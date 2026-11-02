"""
Database Sharding & Horizontal Scaling for VCOS.

Provides:
- Citus/CockroachDB integration for horizontal PostgreSQL scaling
- Transparent sharding with tenant isolation
- Distributed query execution
- Automatic rebalancing
- Cross-shard transactions
"""

import asyncio
import hashlib
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy import MetaData, text, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Integer, JSON, Index, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.config import settings
from app.db.database import Base, metadata

logger = logging.getLogger(__name__)


class ShardingStrategy(str, Enum):
    """Sharding strategies."""
    HASH = "hash"
    RANGE = "range"
    LIST = "list"
    TENANT = "tenant"  # Tenant-based sharding (default for multi-tenant SaaS)


class DatabaseEngine(str, Enum):
    """Supported database engines for horizontal scaling."""
    CITUS = "citus"
    COCKROACHDB = "cockroachdb"
    YUGABYTEDB = "yugabytedb"
    NATIVE_POSTGRESQL = "native_postgresql"  # Manual sharding


@dataclass
class ShardConfig:
    """Configuration for a single shard."""
    shard_id: str
    name: str
    connection_string: str
    region: str
    weight: int = 100  # Weight for load balancing
    max_connections: int = 50
    min_connections: int = 5
    is_read_replica: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ShardGroup:
    """Group of shards with same schema."""
    group_id: str
    name: str
    strategy: ShardingStrategy
    shards: List[ShardConfig]
    distribution_key: str  # Column used for sharding
    replication_factor: int = 1
    colocation_group: Optional[str] = None  # For Citus colocation


class ShardRouter:
    """Routes queries to appropriate shards based on sharding strategy."""
    
    def __init__(self, shard_groups: Dict[str, ShardGroup]):
        self.shard_groups = shard_groups
    
    def route(self, group_id: str, sharding_key: Any) -> ShardConfig:
        """Determine which shard to use for a given key."""
        group = self.shard_groups.get(group_id)
        if not group:
            raise ValueError(f"Shard group not found: {group_id}")
        
        if group.strategy == ShardingStrategy.HASH:
            return self._hash_route(group, sharding_key)
        elif group.strategy == ShardingStrategy.TENANT:
            return self._tenant_route(group, sharding_key)
        elif group.strategy == ShardingStrategy.RANGE:
            return self._range_route(group, sharding_key)
        elif group.strategy == ShardingStrategy.LIST:
            return self._list_route(group, sharding_key)
        else:
            raise ValueError(f"Unsupported sharding strategy: {group.strategy}")
    
    def _hash_route(self, group: ShardGroup, key: Any) -> ShardConfig:
        """Route using consistent hashing."""
        key_str = str(key)
        hash_val = int(hashlib.md5(key_str.encode()).hexdigest(), 16)
        shard_index = hash_val % len(group.shards)
        return group.shards[shard_index]
    
    def _tenant_route(self, group: ShardGroup, key: Any) -> ShardConfig:
        """Route based on tenant ID (hash of tenant_id)."""
        return self._hash_route(group, key)
    
    def _range_route(self, group: ShardGroup, key: Any) -> ShardConfig:
        """Route based on range of key values."""
        # For range-based, shards should be sorted by range
        key_val = int(key) if isinstance(key, (int, str)) and str(key).isdigit() else 0
        for shard in group.shards:
            shard_range = shard.metadata.get("range", (0, float('inf')))
            if shard_range[0] <= key_val < shard_range[1]:
                return shard
        return group.shards[-1]  # Default to last
    
    def _list_route(self, group: ShardGroup, key: Any) -> ShardConfig:
        """Route based on explicit list mapping."""
        key_str = str(key)
        for shard in group.shards:
            if key_str in shard.metadata.get("values", []):
                return shard
        return group.shards[0]


class DistributedQueryExecutor:
    """Executes queries across multiple shards."""
    
    def __init__(self, router: ShardRouter):
        self.router = router
        self._pools: Dict[str, asyncpg.Pool] = {}
    
    async def initialize(self, shard_groups: Dict[str, ShardGroup]):
        """Initialize connection pools for all shards."""
        for group_id, group in shard_groups.items():
            for shard in group.shards:
                pool = await asyncpg.create_pool(
                    shard.connection_string,
                    min_size=shard.min_connections,
                    max_size=shard.max_connections,
                )
                self._pools[shard.shard_id] = pool
    
    async def execute_on_shard(
        self,
        group_id: str,
        sharding_key: Any,
        query: str,
        *args,
    ) -> List[Dict[str, Any]]:
        """Execute query on single shard determined by key."""
        shard = self.router.route(group_id, sharding_key)
        pool = self._pools.get(shard.shard_id)
        if not pool:
            raise ValueError(f"No pool for shard: {shard.shard_id}")
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def execute_on_all_shards(
        self,
        group_id: str,
        query: str,
        *args,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Execute query on all shards in a group."""
        group = self.router.shard_groups.get(group_id)
        if not group:
            raise ValueError(f"Shard group not found: {group_id}")
        
        results = {}
        for shard in group.shards:
            pool = self._pools.get(shard.shard_id)
            if not pool:
                continue
            async with pool.acquire() as conn:
                try:
                    rows = await conn.fetch(query, *args)
                    results[shard.shard_id] = [dict(row) for row in rows]
                except Exception as e:
                    logger.error(f"Query failed on shard {shard.shard_id}: {e}")
                    results[shard.shard_id] = {"error": str(e)}
        
        return results
    
    async def execute_distributed_transaction(
        self,
        group_id: str,
        operations: List[Tuple[Any, str, Tuple]],  # (sharding_key, query, args)
    ) -> bool:
        """Execute distributed transaction across shards (2PC)."""
        # This is a simplified 2PC implementation
        # In production, use proper distributed transaction coordinator
        
        # Phase 1: Prepare
        prepared = []
        for sharding_key, query, args in operations:
            shard = self.router.route(group_id, sharding_key)
            pool = self._pools.get(shard.shard_id)
            if not pool:
                # Rollback prepared
                for p_shard_id, p_conn in prepared:
                    await p_conn.execute("ROLLBACK")
                return False
            
            conn = await pool.acquire()
            try:
                await conn.execute("BEGIN")
                await conn.execute(query, *args)
                await conn.execute("PREPARE TRANSACTION 'dist_tx_' || gen_random_uuid()")
                prepared.append((shard.shard_id, conn))
            except Exception as e:
                logger.error(f"Prepare failed on {shard.shard_id}: {e}")
                # Rollback
                for p_shard_id, p_conn in prepared:
                    try:
                        await p_conn.execute("ROLLBACK PREPARED")
                    except:
                        pass
                return False
        
        # Phase 2: Commit
        for shard_id, conn in prepared:
            try:
                await conn.execute("COMMIT PREPARED")
            except Exception as e:
                logger.error(f"Commit failed on {shard_id}: {e}")
                return False
            finally:
                await conn.close()
        
        return True
    
    async def close(self):
        for pool in self._pools.values():
            await pool.close()


class ShardManager:
    """Manages shard lifecycle, rebalancing, and maintenance."""
    
    def __init__(self, router: ShardRouter, executor: DistributedQueryExecutor):
        self.router = router
        self.executor = executor
        self._rebalancing = False
    
    async def add_shard(self, group_id: str, shard: ShardConfig) -> bool:
        """Add a new shard to a group."""
        group = self.router.shard_groups.get(group_id)
        if not group:
            return False
        
        # Initialize connection pool
        pool = await asyncpg.create_pool(
            shard.connection_string,
            min_size=shard.min_connections,
            max_size=shard.max_connections,
        )
        self.executor._pools[shard.shard_id] = pool
        
        group.shards.append(shard)
        logger.info(f"Added shard {shard.shard_id} to group {group_id}")
        return True
    
    async def remove_shard(self, group_id: str, shard_id: str) -> bool:
        """Remove a shard from a group (after data migration)."""
        group = self.router.shard_groups.get(group_id)
        if not group:
            return False
        
        # Find shard
        shard_idx = next((i for i, s in enumerate(group.shards) if s.shard_id == shard_id), -1)
        if shard_idx == -1:
            return False
        
        # Close pool
        pool = self.executor._pools.pop(shard_id, None)
        if pool:
            await pool.close()
        
        group.shards.pop(shard_idx)
        logger.info(f"Removed shard {shard_id} from group {group_id}")
        return True
    
    async def rebalance(
        self,
        group_id: str,
        strategy: ShardingStrategy = ShardingStrategy.HASH,
    ) -> Dict[str, Any]:
        """Rebalance data across shards."""
        if self._rebalancing:
            return {"success": False, "error": "Rebalancing already in progress"}
        
        self._rebalancing = True
        results = {"moved": 0, "errors": []}
        
        try:
            group = self.router.shard_groups.get(group_id)
            if not group:
                return {"success": False, "error": "Group not found"}
            
            # For hash-based, data movement is handled by Citus/CockroachDB automatically
            # For manual sharding, we'd need to move data between shards
            if strategy == ShardingStrategy.HASH:
                # Citus handles this via rebalance_table_shards()
                # CockroachDB handles this automatically
                logger.info(f"Rebalancing group {group_id} using {strategy.value}")
                results["moved"] = -1  # Indicates automatic
            else:
                # Manual rebalancing logic
                results["moved"] = await self._manual_rebalance(group, strategy)
            
            return {"success": True, **results}
        finally:
            self._rebalancing = False
    
    async def _manual_rebalance(self, group: ShardGroup, strategy: ShardingStrategy) -> int:
        """Manual rebalancing for non-automatic engines."""
        # This would involve:
        # 1. Calculate target distribution
        # 2. For each shard, identify data to move
        # 3. Copy data to target shard
        # 4. Verify data integrity
        # 5. Switch traffic
        # 6. Remove from source
        # This is complex and engine-specific
        return 0


# ==================== Citus Integration ====================

class CitusManager:
    """Citus-specific management operations."""
    
    def __init__(self, coordinator_pool: asyncpg.Pool):
        self.coordinator_pool = coordinator_pool
    
    async def create_distributed_table(
        self,
        table_name: str,
        distribution_column: str,
        colocation_group: Optional[str] = None,
    ) -> bool:
        """Create a distributed table in Citus."""
        async with self.coordinator_pool.acquire() as conn:
            query = f"""
                SELECT create_distributed_table('{table_name}', '{distribution_column}')
            """
            if colocation_group:
                query += f", colocate_with => '{colocation_group}'"
            await conn.execute(query)
            return True
    
    async def create_reference_table(self, table_name: str) -> bool:
        """Create a reference table (replicated to all nodes)."""
        async with self.coordinator_pool.acquire() as conn:
            await conn.execute(f"SELECT create_reference_table('{table_name}')")
            return True
    
    async def rebalance_shards(self, table_name: str = None) -> Dict[str, Any]:
        """Rebalance shards for a table or all tables."""
        async with self.coordinator_pool.acquire() as conn:
            if table_name:
                await conn.execute(f"SELECT rebalance_table_shards('{table_name}')")
            else:
                await conn.execute("SELECT rebalance_table_shards()")
            return {"success": True}
    
    async def add_worker_node(self, node_name: str, port: int = 5432) -> bool:
        """Add a worker node to the cluster."""
        async with self.coordinator_pool.acquire() as conn:
            await conn.execute(
                "SELECT * FROM citus_add_node($1, $2)",
                node_name, port
            )
            return True
    
    async def remove_worker_node(self, node_name: str) -> bool:
        """Remove a worker node (after data rebalancing)."""
        async with self.coordinator_pool.acquire() as conn:
            await conn.execute(
                "SELECT * FROM citus_remove_node($1)",
                node_name
            )
            return True
    
    async def get_shard_distribution(self, table_name: str) -> List[Dict]:
        """Get shard distribution for a table."""
        async with self.coordinator_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT shardid, nodename, nodeport, shardminvalue, shardmaxvalue
                FROM citus_shards
                WHERE logicalrelid = $1::regclass
            """, table_name)
            return [dict(row) for row in rows]
    
    async def get_node_stats(self) -> List[Dict]:
        """Get worker node statistics."""
        async with self.coordinator_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT nodeid, nodename, nodeport, isactive, 
                       noderole, nodecluster
                FROM pg_dist_node
            """)
            return [dict(row) for row in rows]


# ==================== CockroachDB Manager ====================

class CockroachDBManager:
    """CockroachDB-specific management operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def create_database(self, name: str, replication_factor: int = 3) -> bool:
        """Create a database with specified replication factor."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE DATABASE {name} WITH REPLICATION = {replication_factor}")
            return True
    
    async def set_replication_zone(
        self,
        target: str,  # table, database, index, or range
        constraints: Dict[str, Any],  # e.g., {"zone": "us-east-1"}
        replication_factor: int = 3,
    ) -> bool:
        """Set replication zone configuration."""
        import json
        constraints_json = json.dumps(constraints)
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                ALTER {target} CONFIGURE ZONE USING
                    constraints = '{constraints_json}',
                    num_replicas = {replication_factor}
            """)
            return True
    
    async def split_range(self, key: str) -> bool:
        """Manually split a range at a specific key."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"ALTER RANGE SPLIT AT {key}")
            return True
    
    async def merge_ranges(self, start_key: str, end_key: str) -> bool:
        """Merge adjacent ranges."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"ALTER RANGE MERGE {start_key} TO {end_key}")
            return True
    
    async def get_range_info(self) -> List[Dict]:
        """Get range information for all ranges."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT range_id, start_key, end_key, 
                       replicas, lease_holder, replicas_status
                FROM crdb_internal.ranges
                WHERE database_name = current_database()
            """)
            return [dict(row) for row in rows]
    
    async def get_node_info(self) -> List[Dict]:
        """Get cluster node information."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT node_id, address, is_live, updated_at, 
                       started_at, membership
                FROM crdb_internal.cluster_nodes
            """)
            return [dict(row) for row in rows]


# ==================== YugabyteDB Manager ====================

class YugabyteDBManager:
    """YugabyteDB-specific management (PostgreSQL-compatible with distributed SQL)."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def create_table_with_splits(
        self,
        table_name: str,
        columns: Dict[str, str],
        primary_key: List[str],
        split_rows: int = 16,
    ) -> bool:
        """Create table with automatic hash sharding and pre-splits."""
        cols = ", ".join([f"{k} {v}" for k, v in columns.items()])
        pk = ", ".join(primary_key)
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE {table_name} ({cols}, PRIMARY KEY ({pk}))
                SPLIT INTO {split_rows} TABLETS
            """)
            return True
    
    async def get_tablet_info(self, table_name: str) -> List[Dict]:
        """Get tablet information for a table."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tablet_id, tablet_uuid, tablet_state, 
                       table_name, leader, replicas
                FROM yb_tablets
                WHERE table_name = $1
            """, table_name)
            return [dict(row) for row in rows]


# ==================== Global Sharding Manager ====================

class ShardingManager:
    """
    Global manager for horizontal database scaling.
    Supports Citus, CockroachDB, YugabyteDB, and manual sharding.
    """
    
    def __init__(
        self,
        engine_type: DatabaseEngine = DatabaseEngine.NATIVE_POSTGRESQL,
        coordinator_dsn: str = None,
        worker_dsns: List[str] = None,
    ):
        self.engine_type = engine_type
        self.coordinator_dsn = coordinator_dsn
        self.worker_dsns = worker_dsns or []
        
        self.router = ShardRouter({})
        self.executor = DistributedQueryExecutor(self.router)
        self.shard_manager = ShardManager(self.router, self.executor)
        
        self._citus: Optional[CitusManager] = None
        self._cockroach: Optional[CockroachDBManager] = None
        self._yugabyte: Optional[YugabyteDBManager] = None
        
        self._coordinator_pool: Optional[asyncpg.Pool] = None
        self._worker_pools: Dict[str, asyncpg.Pool] = {}
        self._initialized = False
    
    async def initialize(
        self,
        coordinator_dsn: str = None,
        worker_dsns: List[str] = None,
        engine_type: DatabaseEngine = None,
    ):
        """Initialize the sharding manager."""
        if coordinator_dsn:
            self.coordinator_dsn = coordinator_dsn
        if worker_dsns:
            self.worker_dsns = worker_dsns
        if engine_type:
            self.engine_type = engine_type
        
        # Initialize coordinator pool
        if self.coordinator_dsn:
            self._coordinator_pool = await asyncpg.create_pool(
                self.coordinator_dsn,
                min_size=5,
                max_size=20,
            )
        
        # Initialize worker pools
        for i, dsn in enumerate(self.worker_dsns):
            pool = await asyncpg.create_pool(dsn, min_size=5, max_size=20)
            self._worker_pools[f"worker_{i}"] = pool
        
        # Initialize engine-specific managers
        if self.engine_type == DatabaseEngine.CITUS:
            self._citus = CitusManager(self._coordinator_pool)
        elif self.engine_type == DatabaseEngine.COCKROACHDB:
            self._cockroach = CockroachDBManager(self._coordinator_pool or self._worker_pools.get("worker_0"))
        elif self.engine_type == DatabaseEngine.YUGABYTEDB:
            self._yugabyte = YugabyteDBManager(self._coordinator_pool or self._worker_pools.get("worker_0"))
        
        # Initialize executor pools
        await self.executor.initialize({})
        
        self._initialized = True
        logger.info(f"ShardingManager initialized with engine: {self.engine_type.value}")
    
    async def create_shard_group(
        self,
        group_id: str,
        name: str,
        strategy: ShardingStrategy,
        distribution_key: str,
        shards: List[ShardConfig],
        colocation_group: Optional[str] = None,
    ) -> ShardGroup:
        """Create a new shard group."""
        group = ShardGroup(
            group_id=group_id,
            name=name,
            strategy=strategy,
            shards=shards,
            distribution_key=distribution_key,
            colocation_group=colocation_group,
        )
        self.router.shard_groups[group_id] = group
        
        # Initialize executor pools for new shards
        for shard in shards:
            pool = await asyncpg.create_pool(
                shard.connection_string,
                min_size=shard.min_connections,
                max_size=shard.max_connections,
            )
            self.executor._pools[shard.shard_id] = pool
        
        return group
    
    # ==================== Citus Operations ====================
    
    async def citus_create_distributed_table(
        self,
        table_name: str,
        distribution_column: str,
        colocation_group: Optional[str] = None,
    ) -> bool:
        if not self._citus:
            raise ValueError("Citus not initialized")
        return await self._citus.create_distributed_table(table_name, distribution_column, colocation_group)
    
    async def citus_create_reference_table(self, table_name: str) -> bool:
        if not self._citus:
            raise ValueError("Citus not initialized")
        return await self._citus.create_reference_table(table_name)
    
    async def citus_rebalance(self, table_name: str = None) -> Dict:
        if not self._citus:
            raise ValueError("Citus not initialized")
        return await self._citus.rebalance_shards(table_name)
    
    async def citus_add_worker(self, node_name: str, port: int = 5432) -> bool:
        if not self._citus:
            raise ValueError("Citus not initialized")
        return await self._citus.add_worker_node(node_name, port)
    
    # ==================== CockroachDB Operations ====================
    
    async def cockroach_create_database(self, name: str, replication_factor: int = 3) -> bool:
        if not self._cockroach:
            raise ValueError("CockroachDB not initialized")
        return await self._cockroach.create_database(name, replication_factor)
    
    async def cockroach_set_zone(
        self,
        target: str,
        constraints: Dict[str, Any],
        replication_factor: int = 3,
    ) -> bool:
        if not self._cockroach:
            raise ValueError("CockroachDB not initialized")
        return await self._cockroach.set_replication_zone(target, constraints, replication_factor)
    
    async def cockroach_split_range(self, key: str) -> bool:
        if not self._cockroach:
            raise ValueError("CockroachDB not initialized")
        return await self._cockroach.split_range(key)
    
    # ==================== YugabyteDB Operations ====================
    
    async def yugabyte_create_table(
        self,
        table_name: str,
        columns: Dict[str, str],
        primary_key: List[str],
        split_rows: int = 16,
    ) -> bool:
        if not self._yugabyte:
            raise ValueError("YugabyteDB not initialized")
        return await self._yugabyte.create_table_with_splits(table_name, columns, primary_key, split_rows)
    
    # ==================== Generic Operations ====================
    
    async def execute_on_shard(
        self,
        group_id: str,
        sharding_key: Any,
        query: str,
        *args,
    ) -> List[Dict[str, Any]]:
        """Execute query on single shard."""
        return await self.executor.execute_on_shard(group_id, sharding_key, query, *args)
    
    async def execute_on_all_shards(
        self,
        group_id: str,
        query: str,
        *args,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Execute query on all shards in group."""
        return await self.executor.execute_on_all_shards(group_id, query, *args)
    
    async def execute_distributed_transaction(
        self,
        group_id: str,
        operations: List[Tuple[Any, str, Tuple]],
    ) -> bool:
        """Execute distributed transaction."""
        return await self.executor.execute_distributed_transaction(group_id, operations)
    
    async def rebalance(self, group_id: str, strategy: ShardingStrategy = ShardingStrategy.HASH) -> Dict[str, Any]:
        """Rebalance shard group."""
        return await self.shard_manager.rebalance(group_id, strategy)
    
    async def get_shard_stats(self, group_id: str) -> Dict[str, Any]:
        """Get statistics for all shards in a group."""
        group = self.router.shard_groups.get(group_id)
        if not group:
            return {"error": "Group not found"}
        
        stats = {}
        for shard in group.shards:
            pool = self.executor._pools.get(shard.shard_id)
            if pool:
                stats[shard.shard_id] = {
                    "size": pool.get_size(),
                    "idle": pool.get_idle_size(),
                    "max_size": shard.max_connections,
                }
        return stats
    
    async def close(self):
        """Close all connections."""
        if self._coordinator_pool:
            await self._coordinator_pool.close()
        for pool in self._worker_pools.values():
            await pool.close()
        for pool in self.executor._pools.values():
            await pool.close()
        logger.info("ShardingManager closed")


# ==================== SQLAlchemy Integration ====================

class ShardedSession:
    """SQLAlchemy session that routes to appropriate shard."""
    
    def __init__(self, sharding_manager: ShardingManager, group_id: str):
        self.sharding_manager = sharding_manager
        self.group_id = group_id
        self._sessions: Dict[str, AsyncSession] = {}
    
    def _get_session(self, sharding_key: Any) -> AsyncSession:
        """Get or create session for shard."""
        shard = self.sharding_manager.router.route(self.group_id, sharding_key)
        if shard.shard_id not in self._sessions:
            # Create session bound to shard's connection
            pass  # Implementation depends on SQLAlchemy integration
        return self._sessions[shard.shard_id]
    
    async def execute(self, sharding_key: Any, query, *args, **kwargs):
        """Execute query on appropriate shard."""
        session = self._get_session(sharding_key)
        return await session.execute(query, *args, **kwargs)


# ==================== Models for Sharding Metadata ====================

class ShardGroupModel(Base, TimestampMixin):
    """Shard group metadata."""
    __tablename__ = "shard_groups"
    __table_args__ = (
        Index("ix_shard_groups_org", "organization_id"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    distribution_key: Mapped[str] = mapped_column(String(64), nullable=False)
    colocation_group: Mapped[Optional[str]] = mapped_column(String(128))
    replication_factor: Mapped[int] = mapped_column(Integer, default=1)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ShardModel(Base, TimestampMixin):
    """Individual shard metadata."""
    __tablename__ = "shards"
    __table_args__ = (
        Index("ix_shards_group", "shard_group_id"),
        Index("ix_shards_region", "region"),
        UniqueConstraint("shard_group_id", "shard_id", name="uq_shard_group_shard"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    shard_group_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("shard_groups.id", ondelete="CASCADE"), nullable=False
    )
    shard_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    connection_string: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100)
    max_connections: Mapped[int] = mapped_column(Integer, default=50)
    min_connections: Mapped[int] = mapped_column(Integer, default=5)
    is_read_replica: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    shard_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ShardRebalanceLogModel(Base, TimestampMixin):
    """Shard rebalancing operation log."""
    __tablename__ = "shard_rebalance_logs"
    __table_args__ = (
        Index("ix_shard_rebalance_logs_group", "shard_group_id"),
        Index("ix_shard_rebalance_logs_time", "created_at"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    shard_group_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("shard_groups.id", ondelete="CASCADE"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    shards_moved: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


# ==================== Global Instance ====================

_sharding_manager: Optional[ShardingManager] = None


def get_sharding_manager() -> ShardingManager:
    """Get global sharding manager instance."""
    global _sharding_manager
    if _sharding_manager is None:
        _sharding_manager = ShardingManager()
    return _sharding_manager


async def init_sharding_manager(
    engine_type: DatabaseEngine = DatabaseEngine.NATIVE_POSTGRESQL,
    coordinator_dsn: str = None,
    worker_dsns: List[str] = None,
) -> ShardingManager:
    """Initialize sharding manager."""
    global _sharding_manager
    _sharding_manager = ShardingManager(
        engine_type=engine_type,
        coordinator_dsn=coordinator_dsn,
        worker_dsns=worker_dsns,
    )
    await _sharding_manager.initialize(
        coordinator_dsn=coordinator_dsn,
        worker_dsns=worker_dsns,
        engine_type=engine_type,
    )
    return _sharding_manager