"""PostgreSQL Capacity Diagnostics for Scale Testing.

Provides comprehensive PostgreSQL server diagnostics for scale testing,
including memory, WAL, connection, and disk diagnostics.
"""

import asyncio
import os
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


@dataclass
class PostgreSQLSettings:
    """Key PostgreSQL settings relevant for scale testing."""
    shared_buffers: str
    work_mem: str
    maintenance_work_mem: str
    max_wal_size: str
    min_wal_size: str
    checkpoint_timeout: str
    checkpoint_completion_target: str
    effective_cache_size: str
    max_connections: int
    autovacuum_max_workers: int
    autovacuum_worker_slots: int
    wal_buffers: str
    synchronous_commit: str
    full_page_writes: str
    wal_compression: str
    fsync: str


@dataclass
class PostgreSQLCapacityMetrics:
    """PostgreSQL capacity and health metrics."""
    timestamp: str
    server_version: str
    max_connections: int
    used_connections: int
    idle_connections: int
    active_connections: int
    waiting_connections: int
    database_size_mb: float
    database_size_bytes: int
    table_sizes: Dict[str, int]
    index_sizes: Dict[str, int]
    total_index_size_mb: float
    wal_files_count: int
    wal_size_mb: float
    checkpoint_stats: Dict[str, Any]
    bgwriter_stats: Dict[str, Any]
    memory_settings: PostgreSQLSettings
    temp_files: Dict[str, Any]
    long_running_queries: List[Dict[str, Any]]
    locks: List[Dict[str, Any]]
    replication_stats: Dict[str, Any]


class PostgreSQLCapacityDiagnostics:
    """Comprehensive PostgreSQL capacity diagnostics for scale testing."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize the diagnostics engine."""
        self.engine = create_async_engine(
            self.db_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
            echo=False,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def close(self):
        """Close the engine."""
        if self.engine:
            await self.engine.dispose()

    async def get_server_settings(self, session: AsyncSession) -> PostgreSQLSettings:
        """Get key PostgreSQL settings."""
        query = """
            SELECT name, setting, unit
            FROM pg_settings
            WHERE name IN (
                'shared_buffers', 'work_mem', 'maintenance_work_mem',
                'max_wal_size', 'min_wal_size', 'checkpoint_timeout',
                'checkpoint_completion_target', 'effective_cache_size',
                'max_connections', 'autovacuum_max_workers',
                'autovacuum_worker_slots', 'wal_buffers',
                'synchronous_commit', 'full_page_writes',
                'wal_compression', 'fsync', 'shared_memory_type'
            )
            ORDER BY name
        """
        result = await session.execute(text(query))
        settings = {row.name: {"setting": row.setting, "unit": row.unit} for row in result}

        def get_setting(name: str, default: str = "") -> str:
            s = settings.get(name, {})
            val = s.get("setting", default)
            unit = s.get("unit", "")
            return f"{val}{unit}" if unit else str(val)

        return PostgreSQLSettings(
            shared_buffers=get_setting("shared_buffers"),
            work_mem=get_setting("work_mem"),
            maintenance_work_mem=get_setting("maintenance_work_mem"),
            max_wal_size=get_setting("max_wal_size"),
            min_wal_size=get_setting("min_wal_size"),
            checkpoint_timeout=get_setting("checkpoint_timeout"),
            checkpoint_completion_target=get_setting("checkpoint_completion_target"),
            effective_cache_size=get_setting("effective_cache_size"),
            max_connections=int(settings.get("max_connections", {}).get("setting", "100")),
            autovacuum_max_workers=int(settings.get("autovacuum_max_workers", {}).get("setting", "3")),
            autovacuum_worker_slots=int(settings.get("autovacuum_worker_slots", {}).get("setting", "3")),
            wal_buffers=get_setting("wal_buffers"),
            synchronous_commit=get_setting("synchronous_commit"),
            full_page_writes=get_setting("full_page_writes"),
            wal_compression=get_setting("wal_compression"),
            fsync=get_setting("fsync"),
        )

    async def get_connection_stats(self, session: AsyncSession) -> Dict[str, int]:
        """Get connection pool statistics."""
        query = """
            SELECT
                count(*) FILTER (WHERE state = 'active') as active,
                count(*) FILTER (WHERE state = 'idle') as idle,
                count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_tx,
                count(*) FILTER (WHERE wait_event_type IS NOT NULL) as waiting,
                count(*) as total
            FROM pg_stat_activity
            WHERE datname = current_database()
        """
        result = await session.execute(text(query))
        row = result.first()
        return {
            "active": row.active or 0,
            "idle": row.idle or 0,
            "idle_in_transaction": row.idle_in_tx or 0,
            "waiting": row.waiting or 0,
            "total": row.total or 0,
        }

    async def get_database_size(self, session: AsyncSession) -> Dict[str, Any]:
        """Get database and table sizes."""
        # Total database size
        db_size_query = """
            SELECT pg_database_size(current_database()) as size_bytes
        """
        result = await session.execute(text(db_size_query))
        db_size_bytes = result.scalar() or 0
        db_size_mb = db_size_bytes / (1024 * 1024)

        # Table sizes
        table_query = """
            SELECT
                relname as table_name,
                pg_total_relation_size(relid) as total_bytes,
                pg_relation_size(relid) as table_bytes,
                pg_total_relation_size(relid) - pg_relation_size(relid) as index_bytes
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY total_bytes DESC
        """
        result = await session.execute(text(table_query))
        table_sizes = {row.table_name: row.total_bytes for row in result}
        index_sizes = {row.table_name: row.index_bytes for row in result}

        # Total index size
        total_index_query = """
            SELECT sum(pg_relation_size(indexrelid)) as index_bytes
            FROM pg_stat_user_indexes
            WHERE schemaname = 'public'
        """
        result = await session.execute(text(total_index_query))
        total_index_bytes = result.scalar() or 0
        total_index_mb = total_index_bytes / (1024 * 1024)

        return {
            "database_size_mb": round(db_size_mb, 2),
            "database_size_bytes": db_size_bytes,
            "table_sizes": table_sizes,
            "index_sizes": index_sizes,
            "total_index_size_mb": round(total_index_mb, 2),
        }

    async def get_wal_stats(self, session: AsyncSession) -> Dict[str, Any]:
        """Get WAL statistics."""
        # WAL files
        wal_files_query = """
            SELECT count(*) as count, sum(size) as size_bytes
            FROM pg_ls_wal()
        """
        try:
            result = await session.execute(text(wal_files_query))
            row = result.first()
            wal_count = row.count or 0
            wal_size_bytes = row.size_bytes or 0
        except Exception:
            # pg_ls_wal might not be available in older versions
            wal_count = 0
            wal_size_bytes = 0

        # WAL stats from pg_stat_wal
        wal_stats_query = """
            SELECT
                wal_records,
                wal_fpi,
                wal_bytes,
                wal_buffers_full,
                wal_write,
                wal_sync,
                write_time,
                sync_time
            FROM pg_stat_wal
        """
        try:
            result = await session.execute(text(wal_stats_query))
            row = result.first()
            wal_stats = {
                "wal_records": row.wal_records or 0,
                "wal_fpi": row.wal_fpi or 0,
                "wal_bytes": row.wal_bytes or 0,
                "wal_buffers_full": row.wal_buffers_full or 0,
                "wal_write": row.wal_write or 0,
                "wal_sync": row.wal_sync or 0,
                "write_time_ms": row.write_time or 0,
                "sync_time_ms": row.sync_time or 0,
            }
        except Exception:
            wal_stats = {}

        return {
            "wal_files_count": wal_count,
            "wal_size_mb": round(wal_size_bytes / (1024 * 1024), 2),
            "wal_size_bytes": wal_size_bytes,
            "wal_stats": wal_stats,
        }

    async def get_checkpoint_stats(self, session: AsyncSession) -> Dict[str, Any]:
        """Get checkpoint statistics."""
        query = """
            SELECT
                checkpoints_timed,
                checkpoints_req,
                checkpoint_write_time,
                checkpoint_sync_time,
                buffers_checkpoint,
                buffers_clean,
                maxwritten_clean,
                buffers_backend,
                buffers_backend_fsync,
                buffers_alloc
            FROM pg_stat_bgwriter
        """
        result = await session.execute(text(query))
        row = result.first()
        return {
            "checkpoints_timed": row.checkpoints_timed or 0,
            "checkpoints_req": row.checkpoints_req or 0,
            "checkpoint_write_time_ms": row.checkpoint_write_time or 0,
            "checkpoint_sync_time_ms": row.checkpoint_sync_time or 0,
            "buffers_checkpoint": row.buffers_checkpoint or 0,
            "buffers_clean": row.buffers_clean or 0,
            "maxwritten_clean": row.maxwritten_clean or 0,
            "buffers_backend": row.buffers_backend or 0,
            "buffers_backend_fsync": row.buffers_backend_fsync or 0,
            "buffers_alloc": row.buffers_alloc or 0,
        }

    async def get_bgwriter_stats(self, session: AsyncSession) -> Dict[str, Any]:
        """Get background writer statistics."""
        query = """
            SELECT
                checkpoints_timed,
                checkpoints_req,
                buffers_checkpoint,
                buffers_clean,
                maxwritten_clean,
                buffers_backend,
                buffers_backend_fsync,
                buffers_alloc,
                stats_reset
            FROM pg_stat_bgwriter
        """
        result = await session.execute(text(query))
        row = result.first()
        return {
            "checkpoints_timed": row.checkpoints_timed or 0,
            "checkpoints_req": row.checkpoints_req or 0,
            "buffers_checkpoint": row.buffers_checkpoint or 0,
            "buffers_clean": row.buffers_clean or 0,
            "maxwritten_clean": row.maxwritten_clean or 0,
            "buffers_backend": row.buffers_backend or 0,
            "buffers_backend_fsync": row.buffers_backend_fsync or 0,
            "buffers_alloc": row.buffers_alloc or 0,
            "stats_reset": str(row.stats_reset) if row.stats_reset else None,
        }

    async def get_temp_files(self, session: AsyncSession) -> Dict[str, Any]:
        """Get temporary file statistics."""
        query = """
            SELECT
                temp_files,
                temp_bytes
            FROM pg_stat_database
            WHERE datname = current_database()
        """
        result = await session.execute(text(query))
        row = result.first()
        return {
            "temp_files": row.temp_files or 0,
            "temp_bytes": row.temp_bytes or 0,
            "temp_bytes_mb": round((row.temp_bytes or 0) / (1024 * 1024), 2),
        }

    async def get_long_running_queries(self, session: AsyncSession, threshold_ms: int = 1000) -> List[Dict[str, Any]]:
        """Get long-running queries."""
        query = f"""
            SELECT
                pid,
                usename,
                application_name,
                client_addr,
                state,
                query_start,
                now() - query_start as duration,
                LEFT(query, 200) as query_preview
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND state = 'active'
                AND now() - query_start > interval '{threshold_ms} milliseconds'
                AND pid <> pg_backend_pid()
            ORDER BY query_start
        """
        result = await session.execute(text(query))
        queries = []
        for row in result:
            queries.append({
                "pid": row.pid,
                "user": row.usename,
                "application": row.application_name,
                "client": row.client_addr,
                "state": row.state,
                "duration": str(row.duration),
                "query": row.query_preview,
            })
        return queries

    async def get_locks(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """Get current locks."""
        query = """
            SELECT
                pid,
                locktype,
                mode,
                granted,
                relation::regclass as relation,
                page,
                tuple,
                virtualxid,
                transactionid,
                classid,
                objid,
                objsubid,
                virtualtransaction
            FROM pg_locks
            WHERE NOT granted
            ORDER BY pid
        """
        result = await session.execute(text(query))
        locks = []
        for row in result:
            locks.append({
                "pid": row.pid,
                "locktype": row.locktype,
                "mode": row.mode,
                "granted": row.granted,
                "relation": str(row.relation) if row.relation else None,
                "page": row.page,
                "tuple": row.tuple,
            })
        return locks

    async def get_replication_stats(self, session: AsyncSession) -> Dict[str, Any]:
        """Get replication statistics."""
        query = """
            SELECT
                pid,
                application_name,
                client_addr,
                state,
                sync_state,
                write_lag,
                flush_lag,
                replay_lag,
                write_lsn,
                flush_lsn,
                replay_lsn
            FROM pg_stat_replication
        """
        result = await session.execute(text(query))
        replication = []
        for row in result:
            replication.append({
                "pid": row.pid,
                "application": row.application_name,
                "client": row.client_addr,
                "state": row.state,
                "sync_state": row.sync_state,
                "write_lag": str(row.write_lag) if row.write_lag else None,
                "flush_lag": str(row.flush_lag) if row.flush_lag else None,
                "replay_lag": str(row.replay_lag) if row.replay_lag else None,
            })
        return {"replication_slots": replication}

    async def get_server_version(self, session: AsyncSession) -> str:
        """Get PostgreSQL server version."""
        result = await session.execute(text("SELECT version()"))
        return result.scalar() or "unknown"

    async def run_full_diagnostics(self) -> PostgreSQLCapacityMetrics:
        """Run complete diagnostics suite."""
        async with self.session_factory() as session:
            server_version = await self.get_server_version(session)
            memory_settings = await self.get_server_settings(session)
            conn_stats = await self.get_connection_stats(session)
            db_sizes = await self.get_database_size(session)
            wal_stats = await self.get_wal_stats(session)
            checkpoint_stats = await self.get_checkpoint_stats(session)
            bgwriter_stats = await self.get_bgwriter_stats(session)
            temp_files = await self.get_temp_files(session)
            long_queries = await self.get_long_running_queries(session)
            locks = await self.get_locks(session)
            replication = await self.get_replication_stats(session)

            return PostgreSQLCapacityMetrics(
                timestamp=datetime.utcnow().isoformat(),
                server_version=server_version,
                max_connections=0,  # Will be filled from settings
                used_connections=conn_stats.get("total", 0),
                idle_connections=conn_stats.get("idle", 0),
                active_connections=conn_stats.get("active", 0),
                waiting_connections=conn_stats.get("waiting", 0),
                database_size_mb=db_sizes["database_size_mb"],
                database_size_bytes=db_sizes["database_size_bytes"],
                table_sizes=db_sizes["table_sizes"],
                index_sizes=db_sizes["index_sizes"],
                total_index_size_mb=db_sizes["total_index_size_mb"],
                wal_files_count=wal_stats["wal_files_count"],
                wal_size_mb=wal_stats["wal_size_mb"],
                checkpoint_stats=checkpoint_stats,
                bgwriter_stats=bgwriter_stats,
                memory_settings=memory_settings,
                temp_files=temp_files,
                long_running_queries=long_queries,
                locks=locks,
                replication_stats=replication,
            )

    def to_json(self, metrics: PostgreSQLCapacityMetrics) -> str:
        """Convert metrics to JSON."""
        return json.dumps(asdict(metrics), indent=2, default=str)


async def run_diagnostics(db_url: str) -> PostgreSQLCapacityMetrics:
    """Run full PostgreSQL diagnostics."""
    diagnostics = PostgreSQLCapacityDiagnostics(db_url)
    await diagnostics.initialize()
    try:
        return await diagnostics.run_full_diagnostics()
    finally:
        await diagnostics.close()


async def print_diagnostics_report(db_url: str):
    """Print a formatted diagnostics report."""
    metrics = await run_diagnostics(db_url)

    print("=" * 80)
    print("POSTGRESQL CAPACITY DIAGNOSTICS REPORT")
    print("=" * 80)
    print(f"Timestamp: {metrics.timestamp}")
    print(f"Server Version: {metrics.server_version}")
    print()

    print("CONNECTION POOL:")
    print(f"  Active:    {metrics.active_connections}")
    print(f"  Idle:      {metrics.idle_connections}")
    print(f"  Waiting:   {metrics.waiting_connections}")
    print(f"  Total:     {metrics.used_connections} / {metrics.max_connections}")
    print()

    print("DATABASE SIZE:")
    print(f"  Database:  {metrics.database_size_mb:.1f} MB")
    print(f"  Indexes:   {metrics.total_index_size_mb:.1f} MB")
    print(f"  Tables:    {len(metrics.table_sizes)}")
    print()

    print("MEMORY SETTINGS:")
    ms = metrics.memory_settings
    print(f"  shared_buffers:        {ms.shared_buffers}")
    print(f"  work_mem:              {ms.work_mem}")
    print(f"  maintenance_work_mem:  {ms.maintenance_work_mem}")
    print(f"  effective_cache_size:  {ms.effective_cache_size}")
    print(f"  max_wal_size:          {ms.max_wal_size}")
    print(f"  min_wal_size:          {ms.min_wal_size}")
    print(f"  checkpoint_timeout:    {ms.checkpoint_timeout}")
    print(f"  checkpoint_completion: {ms.checkpoint_completion_target}")
    print(f"  autovacuum_max_workers: {ms.autovacuum_max_workers}")
    print()

    print("WAL STATISTICS:")
    print(f"  WAL Files: {metrics.wal_files_count}")
    print(f"  WAL Size:  {metrics.wal_size_mb:.1f} MB")
    ws = metrics.checkpoint_stats
    if ws:
        print(f"  Checkpoints (timed): {ws.get('checkpoints_timed', 0)}")
        print(f"  Checkpoints (req):   {ws.get('checkpoints_req', 0)}")
        print(f"  Checkpoint write time: {ws.get('checkpoint_write_time_ms', 0)} ms")
        print(f"  Checkpoint sync time:  {ws.get('checkpoint_sync_time_ms', 0)} ms")
    print()

    print("TEMP FILES:")
    tf = metrics.temp_files
    print(f"  Temp files: {tf.get('temp_files', 0)}")
    print(f"  Temp size:  {tf.get('temp_bytes_mb', 0):.1f} MB")
    print()

    if metrics.long_running_queries:
        print("LONG RUNNING QUERIES:")
        for q in metrics.long_running_queries[:5]:
            print(f"  PID {q['pid']}: {q['duration']} - {q['query'][:80]}...")
    else:
        print("LONG RUNNING QUERIES: None")

    if metrics.locks:
        print(f"\nBLOCKED LOCKS: {len(metrics.locks)}")
        for lock in metrics.locks[:5]:
            print(f"  PID {lock['pid']}: {lock['locktype']} {lock['mode']} on {lock['relation']}")
    else:
        print("\nBLOCKED LOCKS: None")


if __name__ == "__main__":
    import sys
    db_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
    asyncio.run(print_diagnostics_report(db_url))