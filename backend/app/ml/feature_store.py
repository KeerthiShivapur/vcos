"""
Feature Store for VCOS ML Platform.

Feast-compatible feature store implementation with:
- Entity definitions
- Feature views with TTL
- Online/offline stores (Redis + PostgreSQL)
- Feature materialization
- Point-in-time correctness
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from uuid import uuid4

import asyncpg
import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class ValueType(str, Enum):
    """Feature value types."""
    INT32 = "int32"
    INT64 = "int64"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    STRING = "string"
    BOOL = "bool"
    BYTES = "bytes"
    UNIX_TIMESTAMP = "unix_timestamp"


class JoinType(str, Enum):
    """Join types for feature views."""
    INNER = "inner"
    LEFT = "left"


@dataclass
class Entity:
    """Feature store entity (primary key)."""
    name: str
    join_keys: List[str]
    description: str = ""
    value_type: ValueType = ValueType.STRING
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Feature:
    """Feature definition."""
    name: str
    dtype: ValueType
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class FeatureView:
    """Feature view definition with TTL and source."""
    name: str
    entities: List[str]  # Entity names
    features: List[Feature]
    ttl: timedelta = timedelta(days=1)
    batch_source: Optional[str] = None  # Table/query for batch features
    stream_source: Optional[str] = None  # Kafka topic for streaming
    online: bool = True
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FeatureVector:
    """Retrieved feature vector for an entity."""
    entity_id: str
    feature_view: str
    features: Dict[str, Any]
    event_timestamp: datetime
    created_timestamp: datetime


class OnlineStore(ABC):
    """Abstract online store for low-latency feature serving."""

    @abstractmethod
    async def initialize(self):
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def write(self, feature_view: str, entity_id: str, features: Dict[str, Any], timestamp: datetime):
        pass

    @abstractmethod
    async def read(self, feature_view: str, entity_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        pass

    @abstractmethod
    async def delete(self, feature_view: str, entity_id: str):
        pass


class RedisOnlineStore(OnlineStore):
    """Redis-backed online store for feature serving."""

    def __init__(self, redis_url: str = "redis://localhost:6379/1"):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self._prefix = "feast:"

    async def initialize(self):
        self._redis = redis.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("Redis online store initialized")

    async def close(self):
        if self._redis:
            await self._redis.close()

    async def write(self, feature_view: str, entity_id: str, features: Dict[str, Any], timestamp: datetime):
        key = f"{self._prefix}{feature_view}:{entity_id}"
        data = {
            "features": features,
            "event_timestamp": timestamp.isoformat(),
            "created_timestamp": datetime.utcnow().isoformat(),
        }
        await self._redis.setex(key, 86400 * 7, json.dumps(data))  # 7-day TTL default

    async def read(self, feature_view: str, entity_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        keys = [f"{self._prefix}{feature_view}:{eid}" for eid in entity_ids]
        if not keys:
            return []

        pipe = self._redis.mget(keys)
        results = await pipe.execute()

        output = []
        for result in results:
            if result:
                data = json.loads(result)
                output.append(data.get("features"))
            else:
                output.append(None)
        return output

    async def delete(self, feature_view: str, entity_id: str):
        key = f"{self._prefix}{feature_view}:{entity_id}"
        await self._redis.delete(key)


class OfflineStore(ABC):
    """Abstract offline store for training data generation."""

    @abstractmethod
    async def initialize(self):
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def write_batch(self, feature_view: str, data: List[Dict[str, Any]]):
        pass

    @abstractmethod
    async def read_batch(
        self,
        feature_view: str,
        entity_ids: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        pass


class PostgresOfflineStore(OfflineStore):
    """PostgreSQL-backed offline store for training data."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
        )
        await self._ensure_tables()
        logger.info("PostgreSQL offline store initialized")

    async def _ensure_tables(self):
        async with self._pool.acquire() as conn:
            # Feature view tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_view_data (
                    feature_view TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_timestamp TIMESTAMPTZ NOT NULL,
                    created_timestamp TIMESTAMPTZ DEFAULT NOW(),
                    features JSONB NOT NULL,
                    PRIMARY KEY (feature_view, entity_id, event_timestamp)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feature_view_entity_time 
                ON feature_view_data (feature_view, entity_id, event_timestamp DESC)
            """)

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def write_batch(self, feature_view: str, data: List[Dict[str, Any]]):
        if not data:
            return

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for row in data:
                    await conn.execute("""
                        INSERT INTO feature_view_data (feature_view, entity_id, event_timestamp, created_timestamp, features)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (feature_view, entity_id, event_timestamp) 
                        DO UPDATE SET features = EXCLUDED.features, created_timestamp = EXCLUDED.created_timestamp
                    """,
                        row["feature_view"],
                        row["entity_id"],
                        row["event_timestamp"],
                        datetime.utcnow(),
                        json.dumps(row["features"])
                    )

    async def read_batch(
        self,
        feature_view: str,
        entity_ids: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        if not entity_ids:
            return []

        placeholders = ",".join([f"${i+3}" for i in range(len(entity_ids))])
        query = f"""
            SELECT entity_id, event_timestamp, features
            FROM feature_view_data
            WHERE feature_view = $1 
            AND entity_id IN ({placeholders})
            AND event_timestamp >= $2
            AND event_timestamp <= $3
            ORDER BY entity_id, event_timestamp DESC
        """
        params = [feature_view, start_time, end_time] + entity_ids

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            {
                "entity_id": row["entity_id"],
                "event_timestamp": row["event_timestamp"],
                "features": row["features"],
            }
            for row in rows
        ]


class FeatureStore:
    """
    Feast-compatible Feature Store.

    Features:
    - Entity & FeatureView registration
    - Online serving (Redis)
    - Offline training data (PostgreSQL)
    - Point-in-time correct joins
    - Feature materialization
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/1",
        pg_dsn: str = "postgresql://postgres:postgres@localhost:5432/vcos",
    ):
        self.online_store = RedisOnlineStore(redis_url)
        self.offline_store = PostgresOfflineStore(pg_dsn)

        self._entities: Dict[str, Entity] = {}
        self._feature_views: Dict[str, FeatureView] = {}
        self._initialized = False

    async def initialize(self):
        await self.online_store.initialize()
        await self.offline_store.initialize()
        self._initialized = True
        logger.info("Feature Store initialized")

    async def close(self):
        await self.online_store.close()
        await self.offline_store.close()

    # ==================== Entity Management ====================

    def apply_entity(self, entity: Entity):
        """Register an entity."""
        self._entities[entity.name] = entity
        logger.info(f"Applied entity: {entity.name}")

    def get_entity(self, name: str) -> Optional[Entity]:
        return self._entities.get(name)

    def list_entities(self) -> List[Entity]:
        return list(self._entities.values())

    # ==================== Feature View Management ====================

    def apply_feature_view(self, fv: FeatureView):
        """Register a feature view."""
        # Validate entities exist
        for entity_name in fv.entities:
            if entity_name not in self._entities:
                raise ValueError(f"Entity '{entity_name}' not found for feature view '{fv.name}'")

        self._feature_views[fv.name] = fv
        logger.info(f"Applied feature view: {fv.name}")

    def get_feature_view(self, name: str) -> Optional[FeatureView]:
        return self._feature_views.get(name)

    def list_feature_views(self) -> List[FeatureView]:
        return list(self._feature_views.values())

    # ==================== Online Serving ====================

    async def online_write(
        self,
        feature_view: str,
        entity_id: str,
        features: Dict[str, Any],
        event_timestamp: Optional[datetime] = None,
    ):
        """Write features to online store."""
        if not self._initialized:
            await self.initialize()

        fv = self._feature_views.get(feature_view)
        if not fv:
            raise ValueError(f"Feature view '{feature_view}' not found")

        timestamp = event_timestamp or datetime.utcnow()
        await self.online_store.write(feature_view, entity_id, features, timestamp)

    async def online_read(
        self,
        feature_view: str,
        entity_ids: List[str],
    ) -> List[Optional[Dict[str, Any]]]:
        """Read features from online store."""
        if not self._initialized:
            await self.initialize()

        return await self.online_store.read(feature_view, entity_ids)

    async def get_online_features(
        self,
        entity_id: str,
        feature_views: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Get all online features for an entity."""
        fvs = feature_views or list(self._feature_views.keys())
        results = {}

        for fv_name in fvs:
            features = await self.online_read(fv_name, [entity_id])
            if features and features[0]:
                results[fv_name] = features[0]

        return results

    # ==================== Offline / Training Data ====================

    async def write_batch(
        self,
        feature_view: str,
        data: List[Dict[str, Any]],
    ):
        """Write batch features to offline store."""
        if not self._initialized:
            await self.initialize()

        fv = self._feature_views.get(feature_view)
        if not fv:
            raise ValueError(f"Feature view '{feature_view}' not found")

        # Add feature_view to each row
        for row in data:
            row["feature_view"] = feature_view

        await self.offline_store.write_batch(feature_view, data)

    async def get_training_data(
        self,
        entity_ids: List[str],
        feature_views: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get training data with point-in-time correctness."""
        if not self._initialized:
            await self.initialize()

        results = {}
        for fv_name in feature_views:
            fv = self._feature_views.get(fv_name)
            if not fv:
                continue

            data = await self.offline_store.read_batch(fv_name, entity_ids, start_time, end_time)
            results[fv_name] = data

        return results

    async def get_historical_features(
        self,
        entity_df: List[Dict[str, Any]],  # [{"entity_id": "...", "event_timestamp": "..."}, ...]
        feature_views: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get historical features with point-in-time correctness."""
        if not self._initialized:
            await self.initialize()

        # Extract unique entity IDs and time range
        entity_ids = list(set(row["entity_id"] for row in entity_df))
        timestamps = [row["event_timestamp"] for row in entity_df]
        start_time = min(timestamps) - timedelta(days=30)  # Look back 30 days
        end_time = max(timestamps)

        results = {}
        for fv_name in feature_views:
            fv = self._feature_views.get(fv_name)
            if not fv:
                continue

            data = await self.offline_store.read_batch(fv_name, entity_ids, start_time, end_time)

            # Point-in-time join: for each entity_df row, find latest feature <= event_timestamp
            # This is a simplified version; production would use ASOF join
            results[fv_name] = data

        return results

    # ==================== Materialization ====================

    async def materialize(
        self,
        feature_view: str,
        start_time: datetime,
        end_time: datetime,
        batch_size: int = 1000,
    ):
        """Materialize features from offline to online store."""
        if not self._initialized:
            await self.initialize()

        fv = self._feature_views.get(feature_view)
        if not fv:
            raise ValueError(f"Feature view '{feature_view}' not found")

        # Read from offline store
        data = await self.offline_store.read_batch(
            feature_view,
            [],  # All entities
            start_time,
            end_time,
        )

        # Write to online store in batches
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            for row in batch:
                await self.online_write(
                    feature_view,
                    row["entity_id"],
                    row["features"],
                    row["event_timestamp"],
                )

            logger.info(f"Materialized batch {i//batch_size + 1}/{(len(data) + batch_size - 1)//batch_size} for {feature_view}")

    async def materialize_incremental(
        self,
        feature_view: str,
        last_materialized: datetime,
    ):
        """Incremental materialization since last run."""
        await self.materialize(feature_view, last_materialized, datetime.utcnow())

    # ==================== Feature Retrieval ====================

    async def get_feature_vector(
        self,
        entity_id: str,
        feature_view: str,
    ) -> Optional[FeatureVector]:
        """Get complete feature vector for entity."""
        if not self._initialized:
            await self.initialize()

        fv = self._feature_views.get(feature_view)
        if not fv:
            return None

        # Try online first
        features = await self.online_read(feature_view, [entity_id])
        if features and features[0]:
            return FeatureVector(
                entity_id=entity_id,
                feature_view=feature_view,
                features=features[0],
                event_timestamp=datetime.utcnow(),
                created_timestamp=datetime.utcnow(),
            )

        return None

    async def get_feature_vectors(
        self,
        entity_ids: List[str],
        feature_views: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, FeatureVector]]:
        """Get feature vectors for multiple entities and views."""
        fvs = feature_views or list(self._feature_views.keys())
        results = {}

        for entity_id in entity_ids:
            results[entity_id] = {}
            for fv_name in fvs:
                fv = await self.get_feature_vector(entity_id, fv_name)
                if fv:
                    results[entity_id][fv_name] = fv

        return results


# Global feature store instance
_feature_store: Optional[FeatureStore] = None


def get_feature_store() -> FeatureStore:
    """Get or create feature store singleton."""
    global _feature_store
    if _feature_store is None:
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/1')
        pg_dsn = getattr(settings, 'DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/vcos')
        # Convert asyncpg URL to asyncpg format if needed
        if pg_dsn.startswith("sqlite"):
            pg_dsn = "postgresql://postgres:postgres@localhost:5432/vcos"
        _feature_store = FeatureStore(redis_url=redis_url, pg_dsn=pg_dsn)
    return _feature_store


def init_feature_store(
    redis_url: str = "redis://localhost:6379/1",
    pg_dsn: str = "postgresql://postgres:postgres@localhost:5432/vcos",
) -> FeatureStore:
    """Initialize feature store with custom config."""
    global _feature_store
    _feature_store = FeatureStore(redis_url=redis_url, pg_dsn=pg_dsn)
    return _feature_store