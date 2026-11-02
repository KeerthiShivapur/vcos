"""
Redis Cluster Support for VCOS.

Provides:
- Redis Cluster mode (Redis Enterprise / Dragonfly / Valkey)
- Automatic sharding and failover
- Pipeline and transaction support
- Read/write splitting
- Cluster topology management
"""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster as RedisClusterClient
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisClusterMode(str, Enum):
    """Redis cluster modes."""
    NATIVE = "native"           # Redis Cluster mode (Redis 7+)
    SENTINEL = "sentinel"       # Redis Sentinel for HA
    PROXY = "proxy"             # Redis Cluster via proxy (Twemproxy, Redis Proxy)
    DRAGONFLY = "dragonfly"     # Dragonfly (Redis-compatible, multi-threaded)
    VALKEY = "valkey"           # Valkey (Redis fork)


class NodeRole(str, Enum):
    """Redis node roles."""
    MASTER = "master"
    REPLICA = "replica"
    UNKNOWN = "unknown"


@dataclass
class RedisNode:
    """Redis cluster node information."""
    node_id: str
    host: str
    port: int
    role: NodeRole
    master_id: Optional[str] = None
    slots: List[Tuple[int, int]] = field(default_factory=list)
    connected: bool = True
    last_ping: Optional[datetime] = None
    replicated_offset: int = 0
    config_epoch: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClusterConfig:
    """Redis cluster configuration."""
    mode: RedisClusterMode = RedisClusterMode.NATIVE
    startup_nodes: List[Tuple[str, int]] = field(default_factory=list)  # (host, port)
    max_connections_per_node: int = 50
    read_from_replicas: bool = True
    retry_on_timeout: bool = True
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    ssl: bool = False
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    ssl_ca_certs: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    cluster_name: str = "vcos-cluster"
    # Dragonfly/Valkey specific
    enable_multi_thread: bool = True
    # Sentinel specific
    sentinel_master_name: Optional[str] = None
    sentinel_sentinels: List[Tuple[str, int]] = field(default_factory=list)


class RedisClusterManager:
    """
    Manages Redis Cluster connections and operations.
    Supports Redis Cluster, Sentinel, Dragonfly, Valkey, and proxy modes.
    """
    
    def __init__(self, config: ClusterConfig):
        self.config = config
        self._client: Optional[RedisClusterClient] = None
        self._sentinel: Optional[redis.Sentinel] = None
        self._master_client: Optional[Redis] = None
        self._replica_clients: List[Redis] = []
        self._node_cache: Dict[str, RedisNode] = {}
        self._slot_map: Dict[int, str] = {}  # slot -> node_id
        self._initialized = False
        self._refresh_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Initialize cluster connection."""
        if self._initialized:
            return
        
        if self.config.mode == RedisClusterMode.SENTINEL:
            await self._init_sentinel()
        elif self.config.mode in (RedisClusterMode.DRAGONFLY, RedisClusterMode.VALKEY, RedisClusterMode.NATIVE):
            await self._init_native_cluster()
        else:
            raise ValueError(f"Unsupported cluster mode: {self.config.mode}")
        
        # Start background refresh
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        self._initialized = True
        logger.info(f"Redis Cluster Manager initialized (mode: {self.config.mode.value})")
    
    async def _init_sentinel(self):
        """Initialize Redis Sentinel connection."""
        self._sentinel = redis.Sentinel(
            self.config.sentinel_sentinels,
            sentinel_kwargs={
                "socket_timeout": self.config.socket_timeout,
                "socket_connect_timeout": self.config.socket_connect_timeout,
                "username": self.config.username,
                "password": self.config.password,
            }
        )
        
        # Get master and replica clients
        self._master_client = self._sentinel.master_for(
            self.config.sentinel_master_name,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            username=self.config.username,
            password=self.config.password,
        )
        
        self._replica_clients = [
            self._sentinel.slave_for(
                self.config.sentinel_master_name,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                username=self.config.username,
                password=self.config.password,
            )
            for _ in range(3)  # Multiple replica clients for load balancing
        ]
        
        logger.info("Redis Sentinel initialized")
    
    async def _init_native_cluster(self):
        """Initialize native Redis Cluster / Dragonfly / Valkey."""
        # Build startup nodes
        startup_nodes = [
            {"host": host, "port": port}
            for host, port in self.config.startup_nodes
        ]
        
        self._client = RedisClusterClient.from_url(
            f"redis://{startup_nodes[0]['host']}:{startup_nodes[0]['port']}",
            startup_nodes=startup_nodes,
            max_connections_per_node=self.config.max_connections_per_node,
            read_from_replicas=self.config.read_from_replicas,
            retry_on_timeout=self.config.retry_on_timeout,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            ssl=self.config.ssl,
            ssl_certfile=self.config.ssl_certfile,
            ssl_keyfile=self.config.ssl_keyfile,
            ssl_ca_certs=self.config.ssl_ca_certs,
            username=self.config.username,
            password=self.config.password,
            decode_responses=True,
        )
        
        # Fetch initial cluster topology
        await self._refresh_topology()
        logger.info("Native Redis Cluster initialized")
    
    async def _refresh_topology(self):
        """Refresh cluster topology (nodes, slots)."""
        try:
            if self._client:
                # Use CLUSTER NODES and CLUSTER SLOTS
                nodes_info = await self._client.cluster_nodes()
                slots_info = await self._client.cluster_slots()
                
                self._node_cache.clear()
                self._slot_map.clear()
                
                for node_info in nodes_info:
                    node = self._parse_node_info(node_info)
                    self._node_cache[node.node_id] = node
                
                for slot_info in slots_info:
                    start_slot, end_slot, master_info, *replica_infos = slot_info
                    master_id = master_info[2]  # node_id
                    for slot in range(start_slot, end_slot + 1):
                        self._slot_map[slot] = master_id
            
            elif self._sentinel:
                # Refresh sentinel topology
                master_addr = await self._sentinel.discover_master(self.config.sentinel_master_name)
                replicas = await self._sentinel.sentinel_slaves(self.config.sentinel_master_name)
                logger.info(f"Sentinel topology: master={master_addr}, replicas={len(replicas)}")
                
        except Exception as e:
            logger.error(f"Failed to refresh topology: {e}")
    
    def _parse_node_info(self, info: str) -> RedisNode:
        """Parse CLUSTER NODES output line."""
        parts = info.split()
        node_id = parts[0]
        host_port = parts[1]
        flags = parts[2]
        master_id = parts[3] if parts[3] != "-" else None
        # Parse slots
        slots = []
        for part in parts[8:]:
            if "-" in part:
                start, end = part.split("-")
                slots.append((int(start), int(end)))
        
        host, port = host_port.split("@")[0].split(":")
        
        role = NodeRole.UNKNOWN
        if "master" in flags:
            role = NodeRole.MASTER
        elif "slave" in flags or "replica" in flags:
            role = NodeRole.REPLICA
        
        return RedisNode(
            node_id=node_id,
            host=host,
            port=int(port),
            role=role,
            master_id=master_id,
            slots=slots,
        )
    
    async def _refresh_loop(self):
        """Background task to refresh topology periodically."""
        while True:
            try:
                await asyncio.sleep(30)  # Refresh every 30 seconds
                await self._refresh_topology()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Topology refresh error: {e}")
    
    async def close(self):
        """Close all connections."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        if self._client:
            await self._client.close()
        if self._sentinel:
            await self._sentinel.close()
        if self._master_client:
            await self._master_client.close()
        for client in self._replica_clients:
            await client.close()
        self._initialized = False
        logger.info("Redis Cluster Manager closed")
    
    # ==================== Key Operations ====================
    
    def _get_slot(self, key: str) -> int:
        """Calculate hash slot for key (Redis Cluster uses CRC16)."""
        # Redis uses CRC16 with 16384 slots
        return hashlib.crc16(key.encode()) & 0x3FFF  # 16384 slots
    
    def _get_node_for_key(self, key: str) -> Optional[RedisNode]:
        """Get master node responsible for key."""
        slot = self._get_slot(key)
        node_id = self._slot_map.get(slot)
        if node_id:
            return self._node_cache.get(node_id)
        return None
    
    def _get_replica_for_key(self, key: str) -> Optional[Redis]:
        """Get replica client for key (if read_from_replicas)."""
        if not self.config.read_from_replicas:
            return None
        node = self._get_node_for_key(key)
        if node and node.role == NodeRole.MASTER:
            # In cluster mode, replicas serve reads for their master's slots
            pass
        return None
    
    async def get_client_for_key(self, key: str, read_only: bool = False) -> Redis:
        """Get appropriate client for key (master for writes, replica for reads)."""
        if self._client:
            # Cluster mode handles routing automatically
            if read_only and self.config.read_from_replicas:
                # Use READONLY command to allow replica reads
                return self._client  # RedisClusterClient handles routing
            return self._client
        elif self._sentinel:
            if read_only and self._replica_clients:
                # Round-robin replica selection
                import random
                return random.choice(self._replica_clients)
            return self._master_client
        raise RuntimeError("No cluster client available")
    
    # ==================== Basic Operations ====================
    
    async def get(self, key: str, read_only: bool = True) -> Optional[str]:
        """Get value by key."""
        client = await self.get_client_for_key(key, read_only)
        return await client.get(key)
    
    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set key-value pair."""
        client = await self.get_client_for_key(key, read_only=False)
        return await client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
    
    async def delete(self, *keys: str) -> int:
        """Delete keys."""
        client = await self.get_client_for_key(keys[0], read_only=False)
        return await client.delete(*keys)
    
    async def exists(self, *keys: str) -> int:
        """Check if keys exist."""
        client = await self.get_client_for_key(keys[0], read_only=True)
        return await client.exists(*keys)
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set key expiration."""
        client = await self.get_client_for_key(key, read_only=False)
        return await client.expire(key, seconds)
    
    async def ttl(self, key: str) -> int:
        """Get key TTL."""
        client = await self.get_client_for_key(key, read_only=True)
        return await client.ttl(key)
    
    # ==================== Hash Operations ====================
    
    async def hget(self, name: str, key: str, read_only: bool = True) -> Optional[str]:
        client = await self.get_client_for_key(name, read_only)
        return await client.hget(name, key)
    
    async def hset(self, name: str, key: str = None, value: str = None, mapping: Dict = None) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.hset(name, key, value, mapping=mapping)
    
    async def hgetall(self, name: str, read_only: bool = True) -> Dict[str, str]:
        client = await self.get_client_for_key(name, read_only)
        return await client.hgetall(name)
    
    async def hdel(self, name: str, *keys: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.hdel(name, *keys)
    
    async def hexists(self, name: str, key: str, read_only: bool = True) -> bool:
        client = await self.get_client_for_key(name, read_only)
        return await client.hexists(name, key)
    
    # ==================== List Operations ====================
    
    async def lpush(self, name: str, *values: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.lpush(name, *values)
    
    async def rpush(self, name: str, *values: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.rpush(name, *values)
    
    async def lpop(self, name: str, count: int = None, read_only: bool = False) -> Optional[str]:
        client = await self.get_client_for_key(name, read_only)
        return await client.lpop(name, count)
    
    async def rpop(self, name: str, count: int = None, read_only: bool = False) -> Optional[str]:
        client = await self.get_client_for_key(name, read_only)
        return await client.rpop(name, count)
    
    async def lrange(self, name: str, start: int, end: int, read_only: bool = True) -> List[str]:
        client = await self.get_client_for_key(name, read_only)
        return await client.lrange(name, start, end)
    
    # ==================== Set Operations ====================
    
    async def sadd(self, name: str, *values: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.sadd(name, *values)
    
    async def srem(self, name: str, *values: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.srem(name, *values)
    
    async def smembers(self, name: str, read_only: bool = True) -> Set[str]:
        client = await self.get_client_for_key(name, read_only)
        return await client.smembers(name)
    
    async def sismember(self, name: str, value: str, read_only: bool = True) -> bool:
        client = await self.get_client_for_key(name, read_only)
        return await client.sismember(name, value)
    
    # ==================== Sorted Set Operations ====================
    
    async def zadd(self, name: str, mapping: Dict[str, float], read_only: bool = False) -> int:
        client = await self.get_client_for_key(name, read_only)
        return await client.zadd(name, mapping)
    
    async def zrem(self, name: str, *values: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.zrem(name, *values)
    
    async def zrange(
        self,
        name: str,
        start: int,
        end: int,
        desc: bool = False,
        withscores: bool = False,
        read_only: bool = True,
    ) -> List:
        client = await self.get_client_for_key(name, read_only)
        return await client.zrange(name, start, end, desc=desc, withscores=withscores)
    
    async def zscore(self, name: str, value: str, read_only: bool = True) -> Optional[float]:
        client = await self.get_client_for_key(name, read_only)
        return await client.zscore(name, value)
    
    # ==================== Pipeline & Transactions ====================
    
    @asynccontextmanager
    async def pipeline(self, transaction: bool = True):
        """Create pipeline for batch operations."""
        if self._client:
            async with self._client.pipeline(transaction=transaction) as pipe:
                yield pipe
        elif self._master_client:
            async with self._master_client.pipeline(transaction=transaction) as pipe:
                yield pipe
        else:
            raise RuntimeError("No client available")
    
    async def execute_pipeline(self, commands: List[Tuple[str, ...]]) -> List[Any]:
        """Execute multiple commands in pipeline."""
        async with self.pipeline() as pipe:
            for cmd in commands:
                getattr(pipe, cmd[0])(*cmd[1:])
            return await pipe.execute()
    
    # ==================== Pub/Sub ====================
    
    async def publish(self, channel: str, message: str) -> int:
        """Publish message to channel."""
        # For pub/sub, use master or any node
        client = self._master_client or self._client
        if not client:
            raise RuntimeError("No client available for publish")
        return await client.publish(channel, message)
    
    async def subscribe(self, *channels: str):
        """Subscribe to channels."""
        if self._client:
            pubsub = self._client.pubsub()
        else:
            pubsub = self._master_client.pubsub()
        
        await pubsub.subscribe(*channels)
        return pubsub
    
    # ==================== Lua Scripting ====================
    
    def register_script(self, script: str) -> redis.Script:
        """Register Lua script for atomic execution."""
        if self._client:
            return self._client.register_script(script)
        elif self._master_client:
            return self._master_client.register_script(script)
        raise RuntimeError("No client available")
    
    def evalsha(self, sha: str, num_keys: int, *keys_and_args) -> Any:
        """Execute script by SHA."""
        if self._client:
            return self._client.evalsha(sha, *keys_and_args)
        elif self._master_client:
            return self._master_client.evalsha(sha, *keys_and_args)
        raise RuntimeError("No client available")
    
    # ==================== Cluster Management ====================
    
    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get cluster information."""
        if self._client:
            info = await self._client.info("cluster")
            nodes = await self._client.cluster_nodes()
            slots = await self._client.cluster_slots()
            return {
                "mode": self.config.mode.value,
                "cluster_info": info,
                "nodes": len(nodes) if nodes else 0,
                "slots_assigned": len(slots) if slots else 0,
            }
        elif self._sentinel:
            master = await self._sentinel.discover_master(self.config.sentinel_master_name)
            slaves = await self._sentinel.sentinel_slaves(self.config.sentinel_master_name)
            return {
                "mode": "sentinel",
                "master": master,
                "replicas": len(slaves),
            }
        return {"mode": "unknown"}
    
    async def get_node_stats(self) -> List[Dict]:
        """Get statistics for all nodes."""
        if self._client:
            nodes = await self._client.cluster_nodes()
            return [self._parse_node_info(n).__dict__ for n in nodes.split('\n') if n]
        elif self._sentinel:
            master = await self._sentinel.discover_master(self.config.sentinel_master_name)
            replicas = await self._sentinel.sentinel_slaves(self.config.sentinel_master_name)
            return [{"role": "master", "address": master}] + [
                {"role": "replica", "address": f"{r[0]}:{r[1]}"} for r in replicas
            ]
        return []
    
    async def get_keyslot(self, key: str) -> int:
        """Get hash slot for key."""
        return self._get_slot(key)
    
    async def flush_all(self) -> bool:
        """Flush all databases (use with caution!)."""
        if self._client:
            await self._client.flushall()
        elif self._master_client:
            await self._master_client.flushall()
        return True
    
    async def flush_db(self, db: int = 0) -> bool:
        """Flush specific database."""
        if self._client:
            await self._client.flushdb()
        elif self._master_client:
            await self._master_client.flushdb()
        return True
    
    # ==================== Cluster Management (Cluster Mode) ====================
    
    async def add_node(self, host: str, port: int) -> bool:
        """Add new node to cluster."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        await self._client.cluster_meet("localhost", 6379)  # Would need actual host/port
        return True
    
    async def forget_node(self, node_id: str) -> bool:
        """Remove node from cluster."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        await self._client.cluster_forget(node_id)
        return True
    
    async def replicate_node(self, node_id: str, master_id: str) -> bool:
        """Make node replica of master."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        await self._client.cluster_replicate(node_id, master_id)
        return True
    
    async def add_slots(self, node_id: str, *slots: int) -> bool:
        """Assign slots to node."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        await self._client.cluster_addslots(node_id, *slots)
        return True
    
    async def del_slots(self, node_id: str, *slots: int) -> bool:
        """Remove slots from node."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        await self._client.cluster_delslots(node_id, *slots)
        return True
    
    async def rebalance(self, threshold: int = 1) -> bool:
        """Rebalance cluster slots."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        await self._client.cluster_rebalance(threshold=threshold)
        return True
    
    async def reshard(
        self,
        source_nodes: List[str],
        target_node: str,
        slots: int,
    ) -> bool:
        """Reshard slots from source nodes to target."""
        if not self._client:
            raise RuntimeError("Cluster mode required")
        # This would use cluster reshard command
        # Simplified for brevity
        return True
    
    # ==================== Sentinel Management ====================
    
    async def sentinel_get_master(self, master_name: str) -> Tuple[str, int]:
        """Get current master address for master name."""
        if not self._sentinel:
            raise RuntimeError("Sentinel mode required")
        return await self._sentinel.discover_master(master_name)
    
    async def sentinel_failover(self, master_name: str) -> bool:
        """Force failover for master."""
        if not self._sentinel:
            raise RuntimeError("Sentinel mode required")
        await self._sentinel.sentinel_failover(master_name)
        return True
    
    async def sentinel_monitor(
        self,
        name: str,
        ip: str,
        port: int,
        quorum: int,
    ) -> bool:
        """Add master to monitor."""
        if not self._sentinel:
            raise RuntimeError("Sentinel mode required")
        await self._sentinel.sentinel_monitor(name, ip, port, quorum)
        return True
    
    # ==================== Slow Log & Monitoring ====================
    
    async def slowlog_get(self, count: int = 10) -> List[Dict]:
        """Get slow log entries."""
        if self._client:
            return await self._client.slowlog_get(count)
        elif self._master_client:
            return await self._master_client.slowlog_get(count)
        return []
    
    async def slowlog_reset(self) -> bool:
        """Reset slow log."""
        if self._client:
            await self._client.slowlog_reset()
        elif self._master_client:
            await self._master_client.slowlog_reset()
        return True
    
    # ==================== Memory Management ====================
    
    async def memory_usage(self, key: str, samples: int = 0) -> int:
        """Get memory usage for key."""
        client = await self.get_client_for_key(key, read_only=True)
        return await client.memory_usage(key, samples)
    
    async def memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        if self._client:
            return await self._client.info("memory")
        elif self._master_client:
            return await self._master_client.info("memory")
        return {}
    
    # ==================== Geospatial ====================
    
    async def geoadd(self, name: str, longitude: float, latitude: float, member: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.geoadd(name, (longitude, latitude, member))
    
    async def geopos(self, name: str, *members: str) -> List[Tuple[float, float]]:
        client = await self.get_client_for_key(name, read_only=True)
        return await client.geopos(name, *members)
    
    async def geodist(
        self,
        name: str,
        member1: str,
        member2: str,
        unit: str = "m",
    ) -> Optional[float]:
        client = await self.get_client_for_key(name, read_only=True)
        return await client.geodist(name, member1, member2, unit=unit)
    
    async def georadius(
        self,
        name: str,
        longitude: float,
        latitude: float,
        radius: float,
        unit: str = "m",
        withdist: bool = False,
        withcoord: bool = False,
        count: int = None,
        sort: str = "ASC",
    ) -> List:
        client = await self.get_client_for_key(name, read_only=True)
        return await client.georadius(
            name, longitude, latitude, radius,
            unit=unit, withdist=withdist, withcoord=withcoord,
            count=count, sort=sort
        )
    
    # ==================== HyperLogLog ====================
    
    async def pfadd(self, name: str, *values: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.pfadd(name, *values)
    
    async def pfcount(self, *keys: str) -> int:
        client = await self.get_client_for_key(keys[0], read_only=True)
        return await client.pfcount(*keys)
    
    async def pfmerge(self, dest: str, *sources: str) -> bool:
        client = await self.get_client_for_key(dest, read_only=False)
        return await client.pfmerge(dest, *sources)
    
    # ==================== Stream Operations ====================
    
    async def xadd(
        self,
        name: str,
        fields: Dict[str, str],
        id: str = "*",
        maxlen: int = None,
        approximate: bool = True,
    ) -> str:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.xadd(name, fields, id=id, maxlen=maxlen, approximate=approximate)
    
    async def xread(
        self,
        streams: Dict[str, str],
        count: int = None,
        block: int = None,
    ) -> List[Tuple[str, List[Tuple[str, Dict]]]]:
        client = await self.get_client_for_key(list(streams.keys())[0], read_only=True)
        return await client.xread(streams, count=count, block=block)
    
    async def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: Dict[str, str],
        count: int = None,
        block: int = None,
    ) -> List[Tuple[str, List[Tuple[str, Dict]]]]:
        client = await self.get_client_for_key(list(streams.keys())[0], read_only=False)
        return await client.xreadgroup(groupname, consumername, streams, count=count, block=block)
    
    async def xack(self, name: str, groupname: str, *ids: str) -> int:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.xack(name, groupname, *ids)
    
    async def xgroup_create(
        self,
        name: str,
        groupname: str,
        id: str = "0",
        mkstream: bool = False,
    ) -> bool:
        client = await self.get_client_for_key(name, read_only=False)
        return await client.xgroup_create(name, groupname, id=id, mkstream=mkstream)
    
    # ==================== Cluster Metrics ====================
    
    async def get_cluster_metrics(self) -> Dict[str, Any]:
        """Get comprehensive cluster metrics."""
        if self._client:
            info = await self._client.info()
            nodes = await self._client.cluster_nodes()
            slots = await self._client.cluster_slots()
            
            master_count = 0
            replica_count = 0
            slots_covered = 0
            
            for node_info in nodes.split('\n'):
                if not node_info:
                    continue
                if 'master' in node_info:
                    master_count += 1
                elif 'slave' in node_info or 'replica' in node_info:
                    replica_count += 1
            
            for slot_info in slots:
                slots_covered += slot_info[1] - slot_info[0] + 1
            
            return {
                "mode": "cluster",
                "total_nodes": master_count + replica_count,
                "masters": master_count,
                "replicas": replica_count,
                "slots_covered": slots_covered,
                "slots_total": 16384,
                "coverage": slots_covered / 16384 * 100,
            }
        elif self._sentinel:
            master = await self._sentinel.discover_master(self.config.sentinel_master_name)
            replicas = await self._sentinel.sentinel_slaves(self.config.sentinel_master_name)
            return {
                "mode": "sentinel",
                "master": master,
                "replicas": len(replicas),
            }
        
        return {"mode": "unknown"}


# ==================== Redis Cluster Client Factory ====================

def create_redis_cluster(
    mode: RedisClusterMode = RedisClusterMode.NATIVE,
    startup_nodes: List[Tuple[str, int]] = None,
    sentinel_sentinels: List[Tuple[str, int]] = None,
    sentinel_master_name: str = None,
    password: str = None,
    username: str = None,
    ssl: bool = False,
    read_from_replicas: bool = True,
    **kwargs,
) -> RedisClusterManager:
    """Factory function to create RedisClusterManager."""
    
    config = ClusterConfig(
        mode=mode,
        startup_nodes=startup_nodes or [],
        sentinel_sentinels=sentinel_sentinels or [],
        sentinel_master_name=sentinel_master_name,
        password=password,
        username=username,
        ssl=ssl,
        read_from_replicas=read_from_replicas,
        **kwargs,
    )
    
    return RedisClusterManager(config)


# ==================== Global Instance ====================

_redis_cluster_manager: Optional[RedisClusterManager] = None


def get_redis_cluster_manager() -> RedisClusterManager:
    """Get global Redis cluster manager."""
    global _redis_cluster_manager
    if _redis_cluster_manager is None:
        # Default to single-node or read from settings
        config = ClusterConfig(
            mode=RedisClusterMode(getattr(settings, 'REDIS_CLUSTER_MODE', 'native')),
            startup_nodes=getattr(settings, 'REDIS_STARTUP_NODES', [("localhost", 6379)]),
            password=getattr(settings, 'REDIS_PASSWORD', None),
            username=getattr(settings, 'REDIS_USERNAME', None),
            ssl=getattr(settings, 'REDIS_SSL', False),
            read_from_replicas=getattr(settings, 'REDIS_READ_FROM_REPLICAS', True),
        )
        _redis_cluster_manager = RedisClusterManager(config)
    return _redis_cluster_manager


async def init_redis_cluster(
    mode: RedisClusterMode = RedisClusterMode.NATIVE,
    startup_nodes: List[Tuple[str, int]] = None,
    sentinel_sentinels: List[Tuple[str, int]] = None,
    sentinel_master_name: str = None,
    password: str = None,
    username: str = None,
    ssl: bool = False,
    read_from_replicas: bool = True,
    **kwargs,
) -> RedisClusterManager:
    """Initialize Redis cluster manager."""
    global _redis_cluster_manager
    
    config = ClusterConfig(
        mode=mode,
        startup_nodes=startup_nodes or [],
        sentinel_sentinels=sentinel_sentinels or [],
        sentinel_master_name=sentinel_master_name,
        password=password,
        username=username,
        ssl=ssl,
        read_from_replicas=read_from_replicas,
        **kwargs,
    )
    
    _redis_cluster_manager = RedisClusterManager(config)
    await _redis_cluster_manager.initialize()
    return _redis_cluster_manager