"""Isolated Physical Restore Service -- production-grade restore into isolated environment.



Implements:

- Isolated PostgreSQL instance creation

- Physical backup restore (pgbackrest, pg_basebackup)

- WAL replay to target time

- Recovery validation

- Canonical integrity verification

- Safe cleanup

"""



import asyncio

import hashlib

import json

import logging

import os

import shutil

import subprocess

import tempfile

import uuid

from dataclasses import dataclass, field

from datetime import datetime, timezone, timedelta

from enum import Enum

from typing import Any, Dict, List, Optional



from sqlalchemy import select, text

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker



from app.core.timeutils import utcnow

from app.core.config import get_settings

from app.models.backup_manifest import (

    BackupManifest,

    BackupVerificationResult,

    BackupKind,

    BackupStatus,

    RestoreOperation,

    RecoveryManifest,

    RecoveryManifestState,

)

from app.validation.capability_contract import (

    ValidationStatus,

    EnvironmentCapability,

    ValidationCheck,

    ValidationResult,

    CapabilityDetector,

    CapabilityAwareValidator,

)

from app.services.backup_executor import backup_executor

from app.services.wal_archive_monitor import wal_archive_monitor

from app.services.canonical_reality_integrity_service import (

    canonical_reality_integrity_service,

    severity_matches,

)



logger = logging.getLogger("vcos.isolated_restore")





class RestoreMethod(str, Enum):

    """Restore methods."""

    PGBACKREST = "pgbackrest"

    PG_BASEBACKUP = "pg_basebackup"

    PG_RESTORE = "pg_restore"

    UNKNOWN = "unknown"





class IsolatedRestoreState(str, Enum):

    """Isolated restore lifecycle state."""

    INITIALIZING = "initializing"

    CREATING_INSTANCE = "creating_instance"

    RESTORING_BASE_BACKUP = "restoring_base_backup"

    REPLAYING_WAL = "replaying_wal"

    STARTING_POSTGRES = "starting_postgres"

    VALIDATING = "validating"

    CANONICAL_VALIDATION = "canonical_validation"

    COMPLETED = "completed"

    FAILED = "failed"

    CLEANING_UP = "cleaning_up"





@dataclass

class IsolatedRestoreConfig:

    """Configuration for isolated restore."""

    backup_id: str

    target_time: Optional[datetime] = None

    target_lsn: Optional[str] = None

    isolated_port: int = 5433

    isolated_data_dir: str = ""

    postgres_bin_path: str = "/usr/lib/postgresql/18/bin"

    postgres_config: Dict[str, str] = field(default_factory=dict)

    cleanup_on_failure: bool = True

    cleanup_on_success: bool = False  # Keep for inspection by default

    validation_database: str = "postgres"

    validation_organization_id: Optional[str] = None

    wal_archive_dir: Optional[str] = None





@dataclass

class IsolatedRestoreResult:

    """Result of isolated restore operation."""

    success: bool

    restore_id: str

    backup_id: str

    started_at: datetime

    completed_at: Optional[datetime] = None

    state: IsolatedRestoreState = IsolatedRestoreState.INITIALIZING

    isolated_data_dir: str = ""

    isolated_port: int = 0

    postgres_pid: Optional[int] = None

    recovery_target_time: Optional[datetime] = None

    recovery_target_lsn: Optional[str] = None

    wal_files_replayed: int = 0

    validation_results: Dict[str, ValidationResult] = field(default_factory=dict)

    canonical_validation_passed: bool = False

    validation_database: str = "postgres"

    error: Optional[str] = None

    warnings: List[str] = field(default_factory=list)

    execution_log: List[str] = field(default_factory=list)

    

    # Recovery manifest from restored instance

    restored_recovery_manifest: Optional[RecoveryManifest] = None





class IsolatedRestoreService(CapabilityAwareValidator):

    """Isolated physical restore service."""

    

    def __init__(self):

        super().__init__()

        self.settings = get_settings()

        self._active_restores: Dict[str, IsolatedRestoreResult] = {}

    

    def _get_binary_path(self, binary_name: str) -> str:

        """Get the full path to a PostgreSQL binary, checking Windows locations first."""

        if binary_name == "initdb":

            paths = [

                "C:\\Program Files\\PostgreSQL\\18\\bin\\initdb.exe",

                "C:\\Program Files\\PostgreSQL\\17\\bin\\initdb.exe",

                "C:\\Program Files\\PostgreSQL\\16\\bin\\initdb.exe",

                "initdb",

            ]

        elif binary_name == "pg_ctl":

            paths = [

                "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_ctl.exe",

                "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_ctl.exe",

                "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_ctl.exe",

                "pg_ctl",

            ]

        elif binary_name == "pgbackrest":

            paths = [

                "C:\\Program Files\\pgbackrest\\pgbackrest.exe",

                "pgbackrest",

            ]

        elif binary_name == "pg_basebackup":

            paths = [

                "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_basebackup.exe",

                "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_basebackup.exe",

                "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_basebackup.exe",

                "pg_basebackup",

            ]

        elif binary_name == "pg_restore":

            paths = [

                "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_restore.exe",

                "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_restore.exe",

                "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_restore.exe",

                "pg_restore",

            ]

        else:

            paths = [binary_name]



        for path in paths:

            if os.path.exists(path) or shutil.which(path):

                return path

        return binary_name  # fallback

    

    async def create_isolated_restore(

        self,

        db: AsyncSession,

        backup_id: str,

        organization_id: str,

        target_time: Optional[datetime] = None,

        target_lsn: Optional[str] = None,

        config_override: Optional[IsolatedRestoreConfig] = None,

    ) -> IsolatedRestoreResult:

        """Create and execute an isolated physical restore."""

        self.db = db

        self.detector.db = db



        restore_id = f"rst-iso-{uuid.uuid4().hex[:12]}"

        started_at = utcnow()



        # Get backup manifest

        backup = await db.get(BackupManifest, backup_id)

        if not backup:

            return IsolatedRestoreResult(

                success=False,

                restore_id=restore_id,

                backup_id=backup_id,

                started_at=started_at,

                state=IsolatedRestoreState.FAILED,

                error=f"Backup {backup_id} not found",

            )



        # Create restore configuration

        if config_override:

            config = config_override

        else:

            config = IsolatedRestoreConfig(

                backup_id=backup_id,

                target_time=target_time,

                target_lsn=target_lsn,

                isolated_port=self._get_free_port(),

                isolated_data_dir=os.path.join(

                    tempfile.gettempdir(),

                    f"vcos_restore_{restore_id}"

                ),

            )



        result = IsolatedRestoreResult(

            success=False,

            restore_id=restore_id,

            backup_id=backup_id,

            started_at=started_at,

            state=IsolatedRestoreState.INITIALIZING,

            isolated_data_dir=config.isolated_data_dir,

            isolated_port=config.isolated_port,

            recovery_target_time=target_time,

            recovery_target_lsn=target_lsn,

            validation_database=config.validation_database,

        )



        self._active_restores[restore_id] = result



        # Create restore operation record

        restore_op = RestoreOperation(

            id=f"rop-{uuid.uuid4().hex[:12]}",

            backup_id=backup_id,

            organization_id=organization_id,

            restore_id=restore_id,

            target_time=target_time,

            initiated_by="isolated_restore_service",

            phase="RESTORE_INITIALIZED",

            status="in_progress",

            started_at=utcnow(),

        )

        db.add(restore_op)

        await db.flush()



        try:

            # Phase 1: Initialize isolated environment

            await self._phase_initialize(db, restore_op, config, result)

    

            # Phase 2: Create isolated PostgreSQL instance

            await self._phase_create_instance(db, restore_op, config, result)

    

            # Phase 3: Restore base backup

            await self._phase_restore_base_backup(db, restore_op, backup, config, result)

    

            # Phase 4: Configure WAL replay (write recovery settings to auto.conf)

            await self._phase_replay_wal(db, restore_op, backup, config, result)

    

            # Phase 5: Write startup configuration to postgresql.auto.conf (append, not overwrite)

            await self._phase_write_startup_config(db, restore_op, config, result)

    

            # Phase 6: Start PostgreSQL (reads both startup + recovery settings from auto.conf)

            await self._phase_start_postgres(db, restore_op, config, result)

    

            # Phase 7: Validate restored database

            await self._phase_validate(db, restore_op, config, result)

    

            # Phase 7: Canonical integrity validation

            await self._phase_canonical_validation(db, restore_op, config, result)

    

            # Success!

            result.state = IsolatedRestoreState.COMPLETED

            result.success = True

            result.completed_at = utcnow()

    

            restore_op.phase = "ACTIVATED"

            restore_op.status = "completed"

            restore_op.completed_at = utcnow()

            await db.flush()

    

            logger.info(f"Isolated restore {restore_id} completed successfully")

    

        except Exception as e:

            result.state = IsolatedRestoreState.FAILED

            result.error = str(e)

            result.completed_at = utcnow()

    

            restore_op.phase = "FAILED"

            restore_op.status = "failed"

            restore_op.error = str(e)

            restore_op.completed_at = utcnow()

            await db.flush()

    

            logger.error(f"Isolated restore {restore_id} failed: {e}")

    

            # Cleanup on failure

            if config.cleanup_on_failure:

                await self._cleanup(result)



        return result

    

    def _get_free_port(self) -> int:

        """Get a free port for isolated PostgreSQL."""

        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:

            s.bind(('', 0))

            return s.getsockname()[1]

    

    async def _phase_initialize(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 1: Initialize isolated environment."""

        result.state = IsolatedRestoreState.INITIALIZING

        result.execution_log.append("Initializing isolated restore environment...")



        # Create data directory

        os.makedirs(config.isolated_data_dir, exist_ok=True)

        result.execution_log.append(f"Created data directory: {config.isolated_data_dir}")



        # Create restore operation record

        restore_op.phase = "RESTORE_INITIALIZED"

        await db.flush()

    

    async def _phase_create_instance(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 2: Create isolated PostgreSQL instance (initdb)."""

        result.state = IsolatedRestoreState.CREATING_INSTANCE

        result.execution_log.append("Creating isolated PostgreSQL instance...")



        initdb_path = self._get_binary_path("initdb")

        if not shutil.which(initdb_path) and not os.path.exists(initdb_path):

            raise RuntimeError("initdb not found")



        cmd = [

            initdb_path,

            "-D", config.isolated_data_dir,

            "--auth-local=trust",

            "--auth-host=trust",

        ]



        env = os.environ.copy()



        proc = await asyncio.create_subprocess_exec(

            *cmd,

            env=env,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE,

        )

        stdout, stderr = await proc.communicate()



        result.execution_log.append(f"initdb exit code: {proc.returncode}")

        if proc.returncode != 0:

            raise RuntimeError(f"initdb failed: {stderr.decode()[:500]}")



        restore_op.phase = "DATABASE_RESTORED"

        await db.flush()

    

    async def _configure_postgresql(

        self,

        db: AsyncSession,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Write the isolated instance configuration (call AFTER data extraction)."""

        config_file = os.path.join(config.isolated_data_dir, "postgresql.conf")



        # PostgreSQL refuses to start recovery when replica parameters are lower

        # than on the primary, so mirror the primary's settings.

        mirrored = {

            "max_connections": 100,

            "max_wal_senders": 10,

            "max_worker_processes": 8,

            "max_prepared_transactions": 0,

            "max_locks_per_transaction": 64,

        }

        for setting_name in list(mirrored):

            try:

                async with db.begin_nested():

                    value = (await db.execute(text(f"SHOW {setting_name}"))).scalar()

                if value is not None:

                    mirrored[setting_name] = int(str(value))

            except Exception:

                pass



        minimal_config = f"""# VCOS Isolated Restore Configuration

port = {config.isolated_port}

listen_addresses = 'localhost'

max_connections = {mirrored['max_connections']}

shared_buffers = 128MB

wal_level = replica

archive_mode = off

hot_standby = on

max_wal_senders = {mirrored['max_wal_senders']}

max_worker_processes = {mirrored['max_worker_processes']}

max_prepared_transactions = {mirrored['max_prepared_transactions']}

max_locks_per_transaction = {mirrored['max_locks_per_transaction']}

wal_keep_size = '64MB'

logging_collector = off

log_destination = 'stderr'

log_statement = 'none'

log_min_messages = warning

"""



        with open(config_file, "w") as f:

            f.write(minimal_config)



        # Trust-based local access for validation connections (isolated instance only)

        hba_file = os.path.join(config.isolated_data_dir, "pg_hba.conf")

        with open(hba_file, "w") as f:

            f.write(

                "# VCOS Isolated Restore Access Control\n"

                "local   all             all                                     trust\n"

                "host    all             all             127.0.0.1/32            trust\n"

                "host    all             all             ::1/128                 trust\n"

                "local   replication     all                                     trust\n"

                "host    replication     all             127.0.0.1/32            trust\n"

                "host    replication     all             ::1/128                 trust\n"

            )



        result.execution_log.append(f"Isolated configuration written (port={config.isolated_port})")

    

    async def _phase_restore_base_backup(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        backup: BackupManifest,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 3: Restore base backup."""

        result.state = IsolatedRestoreState.RESTORING_BASE_BACKUP

        result.execution_log.append(f"Restoring base backup {backup.id}...")



        if backup.backup_format == "pgbackrest":

            await self._restore_pgbackrest(db, backup, config, result)

        elif backup.backup_format == "pg_basebackup":

            await self._restore_pg_basebackup(db, backup, config, result)

        elif backup.backup_format == "pg_dump":

            # pg_dump creates logical backup - would need pg_restore

            await self._restore_pg_dump(db, backup, config, result)

        else:

            raise RuntimeError(f"Unknown backup format: {backup.backup_format}")



        # The data extraction overwrites any configuration written earlier, so the

        # isolated configuration MUST be (re)applied after the data is in place.

        await self._configure_postgresql(db, config, result)

    

    async def _restore_pgbackrest(

        self,

        db: AsyncSession,

        backup: BackupManifest,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Restore using pgbackrest."""

        pgbackrest_path = self._get_binary_path("pgbackrest")

        cmd = [

            pgbackrest_path,

            "--stanza=vcos",

            "--repo1-path", f"s3://{backup.vault_bucket}",

            "--delta",

            "--target-action=promote",

        ]



        if config.target_time:

            cmd.extend(["--target-time", config.target_time.isoformat()])

        elif config.target_lsn:

            cmd.extend(["--target-lsn", config.target_lsn])



        cmd.append("restore")



        env = os.environ.copy()

        env["PGDATA"] = config.isolated_data_dir



        proc = await asyncio.create_subprocess_exec(

            *cmd,

            env=env,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE,

        )

        stdout, stderr = await proc.communicate()



        result.execution_log.append(f"pgbackrest restore exit code: {proc.returncode}")

        if stdout:

            result.execution_log.append(f"STDOUT: {stdout.decode()[:500]}")

        if stderr:

            result.execution_log.append(f"STDERR: {stderr.decode()[:500]}")



        if proc.returncode != 0:

            raise RuntimeError(f"pgbackrest restore failed: {stderr.decode()[:500]}")

    

    async def _restore_pg_basebackup(

        self,

        db: AsyncSession,

        backup: BackupManifest,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Restore from pg_basebackup (tar format)."""

        if not backup.vault_path or not os.path.exists(backup.vault_path):

            raise RuntimeError(f"Backup path not found: {backup.vault_path}")



        # Extract tar.gz backup with post-extraction integrity verification and retry

        import tarfile

        extracted_files: List[str] = []

        def _extract_archive() -> None:

            with tarfile.open(backup.vault_path, "r:gz") as tar:

                for member in tar:

                    try:

                        tar.extract(member, config.isolated_data_dir, filter="data")

                    except TypeError:

                        tar.extract(member, config.isolated_data_dir)

                    if member.isfile() or member.issym() or member.islnk():

                        extracted_files.append(member.name)

        max_extract_attempts = 3

        missing_files: List[str] = []

        for attempt in range(1, max_extract_attempts + 1):

            extracted_files.clear()

            _extract_archive()

            missing_files = [

                name

                for name in extracted_files

                if not os.path.lexists(os.path.join(config.isolated_data_dir, name))

            ]

            if not missing_files:

                break

            result.execution_log.append(

                f"Post-extraction integrity check failed (attempt {attempt}/{max_extract_attempts}): "

                f"{len(missing_files)} of {len(extracted_files)} files missing, re-extracting"

            )

        if missing_files:

            preview = ", ".join(missing_files[:5])

            raise RuntimeError(

                f"Base backup extraction incomplete after {max_extract_attempts} attempts: "

                f"{len(missing_files)} files missing (e.g. {preview})"

            )

        result.execution_log.append(f"Extracted base backup to {config.isolated_data_dir}")

        result.execution_log.append(

            f"Extraction integrity verified: {len(extracted_files)} files present"

        )



        # Create recovery.signal so PostgreSQL performs recovery on start

        recovery_signal = os.path.join(config.isolated_data_dir, "recovery.signal")

        with open(recovery_signal, "w") as f:

            f.write("")



        result.execution_log.append("Base backup extracted successfully")

    

    async def _restore_pg_dump(

        self,

        db: AsyncSession,

        backup: BackupManifest,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Restore from pg_dump (logical backup)."""

        # This would need a running PostgreSQL instance first

        # For now, we'll start PostgreSQL then pg_restore

        raise NotImplementedError("pg_dump restore not yet implemented")

    

    async def _phase_replay_wal(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        backup: BackupManifest,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 4: Configure WAL replay."""

        result.state = IsolatedRestoreState.REPLAYING_WAL

        result.execution_log.append("Configuring WAL replay...")



        # Create recovery settings in postgresql.auto.conf (PostgreSQL 12+)

        auto_conf = os.path.join(config.isolated_data_dir, "postgresql.auto.conf")



        wal_archive_dir = self._resolve_wal_archive_dir(config)

        restore_command = self._build_restore_command(wal_archive_dir)



        recovery_settings = [

            "archive_mode = off",

            f"restore_command = '{restore_command}'",

        ]



        if config.target_time:

            recovery_settings.append(f"recovery_target_time = '{config.target_time.isoformat()}'")

            recovery_settings.append("recovery_target_action = 'promote'")

        elif config.target_lsn:

            recovery_settings.append(f"recovery_target_lsn = '{config.target_lsn}'")

            recovery_settings.append("recovery_target_action = 'promote'")

        else:

            recovery_settings.append("recovery_target_action = 'promote'")



        with open(auto_conf, "a") as f:

            f.write("\n# VCOS Recovery Configuration\n")

            for setting in recovery_settings:

                f.write(f"{setting}\n")



        result.execution_log.append(

            f"Created recovery configuration (restore_command -> {wal_archive_dir})"

        )

    

    def _resolve_wal_archive_dir(self, config: IsolatedRestoreConfig) -> str:

        """Resolve the WAL archive directory (config > env > settings > platform default)."""

        if config.wal_archive_dir:

            return config.wal_archive_dir

        configured = os.environ.get("WAL_ARCHIVE_DIR") or getattr(

            self.settings, "WAL_ARCHIVE_DIR", None

        )

        if configured:

            return configured

        if os.name == "nt":

            return "C:\\VCOS-Backups\\wal_archive"

        return "/var/lib/vcos/wal_archive"

    

    def _build_restore_command(self, wal_archive_dir: str) -> str:

        """Build a platform-appropriate restore_command for the WAL archive."""

        if os.name == "nt":

            cmd = f'cmd /c copy /y "{wal_archive_dir}\\%f" "%p"'

        else:

            cmd = f'cp "{wal_archive_dir}/%f" "%p"'

        # postgresql.auto.conf parses backslash as an escape character

        return cmd.replace("\\", "\\\\")

    

    async def _phase_write_startup_config(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 5: Write startup configuration to postgresql.auto.conf (append, not overwrite)."""

        result.state = IsolatedRestoreState.STARTING_POSTGRES

        result.execution_log.append(f"Writing startup configuration to postgresql.auto.conf...")



        # Write all postmaster options to postgresql.auto.conf (APPEND, don't overwrite!)

        # This avoids Windows command-line quoting issues with -o parameter.

        auto_conf = os.path.join(config.isolated_data_dir, "postgresql.auto.conf")

        # Mirror the primary postmaster parameters: PostgreSQL refuses



        # recovery when any of these is lower than on the primary.



        mirrored = {



            "max_connections": 100,



            "max_wal_senders": 10,



            "max_worker_processes": 8,



            "max_prepared_transactions": 0,



            "max_locks_per_transaction": 64,



        }



        for setting_name in list(mirrored):



            try:



                async with db.begin_nested():



                    value = (await db.execute(text(f"SHOW {setting_name}"))).scalar()



                if value is not None:



                    mirrored[setting_name] = int(str(value))



            except Exception:



                pass





        startup_config = f"""# VCOS Isolated Restore Startup Configuration



port = {config.isolated_port}



listen_addresses = 'localhost'



max_connections = {mirrored['max_connections']}



shared_buffers = 128MB



wal_level = replica



archive_mode = off



hot_standby = on



max_wal_senders = {mirrored['max_wal_senders']}



max_worker_processes = {mirrored['max_worker_processes']}



max_prepared_transactions = {mirrored['max_prepared_transactions']}



max_locks_per_transaction = {mirrored['max_locks_per_transaction']}



wal_keep_size = '64MB'



logging_collector = off



log_destination = 'stderr'



log_statement = 'none'



log_min_messages = warning



archive_mode = off



"""



        with open(auto_conf, "a") as f:  # Append, don't overwrite!

            f.write("\n# VCOS Isolated Restore Startup Configuration\n")

            f.write(startup_config)



        print(f"DEBUG: Startup config appended to {auto_conf}")

        result.execution_log.append(f"Startup config appended to {auto_conf}")



        # Verify the config file

        with open(auto_conf, "r") as f:

            content = f.read()

            print(f"DEBUG: Config file content:\n{content}")

            if "logging_collector = off" in content:

                print("DEBUG: logging_collector = off found in config")

            else:

                print("WARNING: logging_collector = off NOT found in config!")

            if "log_destination = 'stderr'" in content:

                print("DEBUG: log_destination = 'stderr' found in config")

            else:

                print("WARNING: log_destination = 'stderr' NOT found in config!")

            if f"port = {config.isolated_port}" in content:

                print("DEBUG: port = {config.isolated_port} found in config")

            else:

                print("WARNING: port = {config.isolated_port} NOT found in config!")



        print(f"DEBUG: Minimal config written to {auto_conf}")

        result.execution_log.append(f"Startup config written to {auto_conf}")



        # Verify the config file

        with open(auto_conf, "r") as f:

            content = f.read()

            print(f"DEBUG: Config file content:\n{content}")

            if "logging_collector = off" in content:

                print("DEBUG: logging_collector = off found in config")

            else:

                print("WARNING: logging_collector = off NOT found in config!")

            if "log_destination = 'stderr'" in content:

                print("DEBUG: log_destination = 'stderr' found in config")

            else:

                print("WARNING: log_destination = 'stderr' NOT found in config!")

            if f"port = {config.isolated_port}" in content:

                print("DEBUG: port = {config.isolated_port} found in config")

            else:

                print("WARNING: port = {config.isolated_port} NOT found in config!")



    async def _phase_start_postgres(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 6: Start isolated PostgreSQL instance (config already written by _phase_write_startup_config)."""

        result.state = IsolatedRestoreState.STARTING_POSTGRES

        result.execution_log.append(f"Starting PostgreSQL on port {config.isolated_port}...")

    

        pg_ctl = self._get_binary_path("pg_ctl")

        if not shutil.which(pg_ctl) and not os.path.exists(pg_ctl):

            raise RuntimeError("pg_ctl not found")

    

        # Keep the pg_ctl log OUTSIDE the data directory: Windows blocks pg_ctl

        # from opening a log file that the server itself may also touch.

        pg_ctl_log = os.path.join(

            os.path.dirname(config.isolated_data_dir),

            f"pg_ctl_{os.path.basename(config.isolated_data_dir)}.log",

        )

            

# Start PostgreSQL - no -o parameter needed since config is in auto_conf

        # -W (no wait): pg_ctl's own readiness wait (-w) is unreliable when the

        # server starts in recovery on Windows; readiness is verified by direct

        # connection polling in _wait_for_postgres instead.

        cmd = [

            pg_ctl,

            "-D", config.isolated_data_dir,

            "-l", pg_ctl_log,

            "-W",

            "start",

        ]

            

        env = os.environ.copy()

        

        # NOTE: pg_ctl stdout/stderr must NOT be PIPEs. On Windows the spawned

        # postmaster inherits the pipe write ends, so communicate() would never

        # observe EOF even after pg_ctl itself exits.

        proc = await asyncio.create_subprocess_exec(

            *cmd,

            env=env,

            stdout=asyncio.subprocess.DEVNULL,

            stderr=asyncio.subprocess.DEVNULL,

        )

        pg_ctl_timed_out = False

        try:

            await asyncio.wait_for(proc.communicate(), timeout=330)

        except asyncio.TimeoutError:

            pg_ctl_timed_out = True

            try:

                proc.kill()

                await proc.wait()

            except Exception:

                pass

            result.execution_log.append(

                "pg_ctl did not exit within 330s; terminated the waiter and "

                "will verify readiness by direct connection polling"

            )



        result.execution_log.append(f"pg_ctl start exit code: {proc.returncode}")



        if not pg_ctl_timed_out and proc.returncode != 0:

            # pg_ctl reported failure; only fail the restore if the server is

            # genuinely unreachable.

            if not await self._probe_postgres(config):

                log_content = ""

                if os.path.exists(pg_ctl_log):

                    with open(pg_ctl_log, "r") as f:

                        log_content = f.read()[-2000:]  # Last 2000 chars

                raise RuntimeError(

                    f"pg_ctl start failed (exit {proc.returncode}). Log: {log_content}"

                )

            result.warnings.append(

                f"pg_ctl start reported exit code {proc.returncode} but the server "

                "is reachable; continuing"

            )



        # Wait for PostgreSQL to be ready

        await self._wait_for_postgres(config, result)



        # Get PID

        pid_file = os.path.join(config.isolated_data_dir, "postmaster.pid")

        if os.path.exists(pid_file):

            with open(pid_file, "r") as f:

                result.postgres_pid = int(f.readline().strip())



        result.execution_log.append(f"PostgreSQL started (PID: {result.postgres_pid})")

    

    async def _probe_postgres(self, config: IsolatedRestoreConfig) -> bool:

        """Single fast readiness probe against the isolated instance."""

        import asyncpg



        try:

            conn = await asyncpg.connect(

                host="localhost",

                port=config.isolated_port,

                user="postgres",

                password="postgres",

                database="postgres",

                timeout=5,

            )

            await conn.close()

            return True

        except Exception:

            return False

    

    async def _wait_for_postgres(

        self,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

        timeout: int = 600,

    ) -> None:

        """Wait for PostgreSQL to be ready."""

        start = utcnow()

        while (utcnow() - start).total_seconds() < timeout:

            if await self._probe_postgres(config):

                return

            await asyncio.sleep(1)



        pg_ctl_log = os.path.join(

            os.path.dirname(config.isolated_data_dir),

            f"pg_ctl_{os.path.basename(config.isolated_data_dir)}.log",

        )

        log_content = ""

        try:

            if os.path.exists(pg_ctl_log):

                with open(pg_ctl_log, "r", errors="replace") as f:

                    log_content = f.read()[-2000:]

        except Exception:

            pass

        raise RuntimeError(

            f"PostgreSQL did not start within {timeout} seconds. Log: {log_content}"

        )

    

    async def _phase_validate(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 6: Validate restored database."""

        result.state = IsolatedRestoreState.VALIDATING

        result.execution_log.append("Validating restored database...")



        # Create connection to isolated instance

        isolated_engine = create_async_engine(

            f"postgresql+asyncpg://postgres:postgres@localhost:{config.isolated_port}/{config.validation_database}",

            pool_pre_ping=True,

        )

        isolated_session = async_sessionmaker(isolated_engine, expire_on_commit=False)()



        try:

            # Basic connectivity

            await isolated_session.execute(text("SELECT 1"))

            result.execution_log.append("Database connectivity: OK")

    

            # Check database system identifier matches

            sys_id_result = await isolated_session.execute(text("SELECT system_identifier FROM pg_control_system()"))

            restored_sys_id = sys_id_result.scalar()

            result.execution_log.append(f"Restored system identifier: {restored_sys_id}")

    

            # Check tables exist

            tables_result = await isolated_session.execute(text("""

                SELECT COUNT(*) FROM information_schema.tables 

                WHERE table_schema = 'public'

            """))

            table_count = tables_result.scalar() or 0

            result.execution_log.append(f"Tables found: {table_count}")

    

            if table_count == 0:

                raise RuntimeError("No tables found in restored database")

    

        finally:

            await isolated_session.close()

            await isolated_engine.dispose()

    

    async def _phase_canonical_validation(

        self,

        db: AsyncSession,

        restore_op: RestoreOperation,

        config: IsolatedRestoreConfig,

        result: IsolatedRestoreResult,

    ) -> None:

        """Phase 7: Canonical integrity validation on restored database."""

        result.state = IsolatedRestoreState.CANONICAL_VALIDATION

        result.execution_log.append("Running canonical integrity validation...")



        # Create connection to isolated instance

        isolated_engine = create_async_engine(

            f"postgresql+asyncpg://postgres:postgres@localhost:{config.isolated_port}/{config.validation_database}",

            pool_pre_ping=True,

        )

        isolated_session = async_sessionmaker(isolated_engine, expire_on_commit=False)()



        try:

            self.detector.db = isolated_session

    

            # Run canonical integrity scan

            findings = await canonical_reality_integrity_service.run_integrity_scan(

                db=isolated_session,

                organization_id=config.validation_organization_id or "restore_validation",

                checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],

                limit=100,

            )

    

            # Check for critical findings

            critical_findings = [f for f in findings if severity_matches(f, "CRITICAL")]

            high_findings = [f for f in findings if severity_matches(f, "HIGH")]

    

            result.execution_log.append(f"Canonical integrity scan: {len(findings)} findings ({len(critical_findings)} critical, {len(high_findings)} high)")

    

            if critical_findings:

                result.canonical_validation_passed = False

                result.warnings.append(f"Critical canonical integrity findings: {len(critical_findings)}")

                for finding in critical_findings[:5]:

                    result.warnings.append(f"  CRITICAL: {finding.title} - {finding.description}")

            else:

                result.canonical_validation_passed = True

                result.execution_log.append("Canonical integrity validation: PASSED")

    

            # Store validation results

            result.validation_results["canonical_integrity"] = ValidationResult(

                domain="canonical_integrity",

                overall_status=ValidationStatus.VERIFIED if result.canonical_validation_passed else ValidationStatus.FAILED,

                checks=[],

                message="Canonical integrity validation " + ("passed" if result.canonical_validation_passed else "failed"),

            )

    

        finally:

            await isolated_session.close()

            await isolated_engine.dispose()

    

    async def _cleanup(self, result: IsolatedRestoreResult) -> None:

        """Clean up isolated restore resources."""

        result.state = IsolatedRestoreState.CLEANING_UP



        # Stop PostgreSQL if running

        if result.postgres_pid:

            try:

                # Use pg_ctl stop

                pg_ctl = self._get_binary_path("pg_ctl")

                cmd = [pg_ctl, "-D", result.isolated_data_dir, "stop", "-m", "fast"]

                proc = await asyncio.create_subprocess_exec(*cmd)

                await proc.communicate()

            except Exception:

                pass



        # Remove data directory

        if os.path.exists(result.isolated_data_dir):

            try:

                shutil.rmtree(result.isolated_data_dir)

                result.execution_log.append(f"Cleaned up data directory: {result.isolated_data_dir}")

            except Exception as e:

                result.warnings.append(f"Failed to clean up data directory: {e}")

    

    def get_active_restores(self) -> Dict[str, IsolatedRestoreResult]:

        """Get all active restores."""

        return self._active_restores

    

    def get_restore(self, restore_id: str) -> Optional[IsolatedRestoreResult]:

        """Get a specific restore by ID."""

        return self._active_restores.get(restore_id)

    

    async def stop_isolated_restore(

        self,

        restore_id: str,

        remove_data_dir: bool = False,

    ) -> bool:

        """Stop a running isolated instance (optionally removing its data directory)."""

        result = self._active_restores.get(restore_id)

        if not result or not result.postgres_pid:

            return False



        try:

            pg_ctl = self._get_binary_path("pg_ctl")

            cmd = [pg_ctl, "-D", result.isolated_data_dir, "stop", "-m", "fast"]

            proc = await asyncio.create_subprocess_exec(

                *cmd,

                stdout=asyncio.subprocess.PIPE,

                stderr=asyncio.subprocess.PIPE,

            )

            await proc.communicate()

            result.postgres_pid = None

            result.execution_log.append("Isolated PostgreSQL stopped")

        except Exception as e:

            result.warnings.append(f"Failed to stop isolated PostgreSQL: {e}")

            return False



        if remove_data_dir and os.path.exists(result.isolated_data_dir):

            try:

                shutil.rmtree(result.isolated_data_dir)

                result.execution_log.append(

                    f"Cleaned up data directory: {result.isolated_data_dir}"

                )

            except Exception as e:

                result.warnings.append(f"Failed to clean up data directory: {e}")



        return True





# Global instance

isolated_restore_service = IsolatedRestoreService()