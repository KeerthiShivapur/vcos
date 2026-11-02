"""
ClickHouse Analytics Database for VCOS.

Provides:
- Columnar storage for analytical queries
- High-performance aggregations
- Materialized views for real-time analytics
- Vector search support
- Time-series optimization
- Data compression
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager

import clickhouse_connect
from clickhouse_connect.driver import Client
from clickhouse_connect.driver.query import QueryResult

from app.core.config import settings

logger = logging.getLogger(__name__)


class ClickHouseEngine(str, Enum):
    """ClickHouse table engines."""
    MERGE_TREE = "MergeTree"
    REPLACING_MERGE_TREE = "ReplacingMergeTree"
    SUMMING_MERGE_TREE = "SummingMergeTree"
    AGGREGATING_MERGE_TREE = "AggregatingMergeTree"
    COLLAPSING_MERGE_TREE = "CollapsingMergeTree"
    VERSIONED_COLLAPSING_MERGE_TREE = "VersionedCollapsingMergeTree"
    GRAPHITE_MERGE_TREE = "GraphiteMergeTree"
    LOG = "Log"
    TINY_LOG = "TinyLog"
    MEMORY = "Memory"
    BUFFER = "Buffer"
    EXTERNAL_DISTRIBUTED = "ExternalDistributed"
    KAFKA = "Kafka"
    RABBITMQ = "RabbitMQ"


class CompressionCodec(str, Enum):
    """Compression codecs."""
    LZ4 = "LZ4"
    ZSTD = "ZSTD"
    DELTA = "DELTA"
    DOUBLE_DELTA = "DOUBLE_DELTA"
    GORILLA = "GORILLA"
    T64 = "T64"
    NONE = "NONE"


@dataclass
class TableColumn:
    """Column definition for ClickHouse table."""
    name: str
    type: str  # ClickHouse type (UInt64, String, DateTime, etc.)
    codec: CompressionCodec = CompressionCodec.LZ4
    default: str = ""
    comment: str = ""
    nullable: bool = False
    primary_key: bool = False


@dataclass
class TableConfig:
    """ClickHouse table configuration."""
    name: str
    columns: List[TableColumn]
    engine: ClickHouseEngine = ClickHouseEngine.MERGE_TREE
    order_by: List[str] = field(default_factory=list)
    partition_by: str = ""
    primary_key: List[str] = field(default_factory=list)
    sample_by: str = ""
    ttl: str = ""
    settings: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    # MergeTree specific
    index_granularity: int = 8192
    merge_with_ttl_timeout: int = 86400
    # ReplicatedMergeTree specific
    replica_path: str = ""
    replica_name: str = ""
    # Kafka engine specific
    kafka_broker_list: str = ""
    kafka_topic_list: str = ""
    kafka_group_name: str = ""
    kafka_format: str = "JSONEachRow"
    # TTL
    ttl_column: str = ""
    ttl_interval: str = ""


class ClickHouseAnalytics:
    """
    ClickHouse Analytics Database Client.
    
    Features:
    - High-performance analytical queries
    - Materialized views for real-time aggregations
    - Vector search with ANN indexes
    - Time-series optimization
    - Data compression and TTL
    - Distributed queries
    - Kafka engine for streaming ingestion
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "",
        database: str = "vcos_analytics",
        secure: bool = False,
        verify: bool = True,
        connect_timeout: int = 10,
        send_receive_timeout: int = 300,
        compress: bool = True,
        settings: Dict[str, Any] = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.secure = secure
        self.verify = verify
        self.connect_timeout = connect_timeout
        self.send_receive_timeout = send_receive_timeout
        self.compress = compress
        self.settings = settings or {}
        
        self._client: Optional[Client] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize ClickHouse connection."""
        if self._initialized:
            return
        
        self._client = clickhouse_connect.get_client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
            secure=self.secure,
            verify=self.verify,
            connect_timeout=self.connect_timeout,
            send_receive_timeout=self.send_receive_timeout,
            compress=self.compress,
            settings=self.settings,
        )
        
        # Create database if not exists
        await self.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
        
        self._initialized = True
        logger.info(f"ClickHouse initialized: {self.host}:{self.port}/{self.database}")
    
    async def close(self):
        """Close connection."""
        if self._client:
            self._client.close()
            self._initialized = False
    
    @property
    def client(self) -> Client:
        if not self._initialized:
            raise RuntimeError("ClickHouse not initialized")
        return self._client
    
    # ==================== Query Execution ====================
    
    async def execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        with_column_types: bool = False,
        with_column_names: bool = True,
    ) -> QueryResult:
        """Execute query."""
        return self.client.query(
            query,
            parameters=parameters,
            with_column_types=with_column_types,
            with_column_names=with_column_names,
        )
    
    async def execute_iter(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        chunk_size: int = 10000,
    ) -> AsyncGenerator[List[Tuple], None]:
        """Execute query and yield results in chunks."""
        return self.client.query_iter(query, parameters=parameters, chunk_size=chunk_size)
    
    async def execute_df(self, query: str, parameters: Optional[Dict[str, Any]] = None):
        """Execute query and return pandas DataFrame."""
        return self.client.query_df(query, parameters=parameters)
    
    async def insert(
        self,
        table: str,
        data: List[Tuple],
        column_names: List[str] = None,
    ) -> int:
        """Insert data into table."""
        return self.client.insert(table, data, column_names=column_names)
    
    async def insert_df(self, table: str, df) -> int:
        """Insert pandas DataFrame."""
        return self.client.insert_df(table, df)
    
    # ==================== Table Management ====================
    
    async def create_table(self, config: TableConfig) -> bool:
        """Create table from configuration."""
        columns = []
        for col in config.columns:
            col_def = f"`{col.name}` {col.type}"
            if col.nullable:
                col_def = f"Nullable({col_def})"
            if col.default:
                col_def += f" DEFAULT {col.default}"
            if col.codec != CompressionCodec.NONE:
                col_def += f" CODEC({col.codec.value})"
            columns.append(col_def)
        
        columns_sql = ",\n    ".join(columns)
        
        # Build engine clause
        engine_clause = self._build_engine_clause(config)
        
        # Partition by
        partition_clause = f"PARTITION BY {config.partition_by}" if config.partition_by else ""
        
        # Order by
        order_by_clause = f"ORDER BY ({', '.join(config.order_by)})" if config.order_by else ""
        
        # Primary key
        primary_key_clause = f"PRIMARY KEY ({', '.join(config.primary_key)})" if config.primary_key else ""
        
        # Sample by
        sample_clause = f"SAMPLE BY {config.sample_by}" if config.sample_by else ""
        
        # TTL
        ttl_clause = f"TTL {config.ttl}" if config.ttl else ""
        
        # Settings
        settings_clause = ""
        if config.settings:
            settings_parts = [f"{k} = '{v}'" for k, v in config.settings.items()]
            settings_clause = f"SETTINGS {', '.join(settings_parts)}"
        
        query = f"""
            CREATE TABLE IF NOT EXISTS {config.name} (
                {columns_sql}
            ) ENGINE = {engine_clause}
            {partition_clause}
            {order_by_clause}
            {primary_key_clause}
            {sample_clause}
            {ttl_clause}
            {settings_clause}
        """
        
        await self.execute(query.strip())
        return True
    
    def _build_engine_clause(self, config: TableConfig) -> str:
        """Build engine clause for CREATE TABLE."""
        if config.engine == ClickHouseEngine.MERGE_TREE:
            return "MergeTree()"
        elif config.engine == ClickHouseEngine.REPLACING_MERGE_TREE:
            version_col = config.settings.get("version_column", "version")
            return f"ReplacingMergeTree({version_col})"
        elif config.engine == ClickHouseEngine.SUMMING_MERGE_TREE:
            return "SummingMergeTree()"
        elif config.engine == ClickHouseEngine.AGGREGATING_MERGE_TREE:
            return "AggregatingMergeTree()"
        elif config.engine == ClickHouseEngine.COLLAPSING_MERGE_TREE:
            sign_col = config.settings.get("sign_column", "sign")
            return f"CollapsingMergeTree({sign_col})"
        elif config.engine == ClickHouseEngine.VERSIONED_COLLAPSING_MERGE_TREE:
            version_col = config.settings.get("version_column", "version")
            sign_col = config.settings.get("sign_column", "sign")
            return f"VersionedCollapsingMergeTree({version_col}, {sign_col})"
        elif config.engine == ClickHouseEngine.REPLICATING_MERGE_TREE:
            return f"ReplicatedMergeTree('{config.replica_path}', '{config.replica_name}')"
        elif config.engine == ClickHouseEngine.KAFKA:
            return f"Kafka('{config.kafka_broker_list}', '{config.kafka_topic_list}', '{config.kafka_group_name}', '{config.kafka_format}')"
        elif config.engine == ClickHouseEngine.LOG:
            return "Log()"
        elif config.engine == ClickHouseEngine.MEMORY:
            return "Memory()"
        elif config.engine == ClickHouseEngine.BUFFER:
            return f"Buffer('{config.settings.get('buffer_database', 'default')}', '{config.settings.get('buffer_table', config.name)}', {config.settings.get('buffer_num_layers', 16)}, {config.settings.get('buffer_min_time', 10)}, {config.settings.get('buffer_max_time', 100)}, {config.settings.get('buffer_min_rows', 10000)}, {config.settings.get('buffer_max_rows', 1000000)}, {config.settings.get('buffer_min_bytes', 10000000)}, {config.settings.get('buffer_max_bytes', 100000000)})"
        else:
            return "MergeTree()"
    
    async def drop_table(self, table: str, if_exists: bool = True) -> bool:
        """Drop table."""
        query = f"DROP TABLE {'IF EXISTS ' if if_exists else ''}{table}"
        await self.execute(query)
        return True
    
    async def truncate_table(self, table: str) -> bool:
        """Truncate table."""
        await self.execute(f"TRUNCATE TABLE {table}")
        return True
    
    async def table_exists(self, table: str) -> bool:
        """Check if table exists."""
        result = await self.execute(
            "SELECT 1 FROM system.tables WHERE database = ? AND name = ?",
            parameters=[self.database, table],
        )
        return len(result.result_rows) > 0
    
    async def get_table_size(self, table: str) -> Dict[str, Any]:
        """Get table size information."""
        result = await self.execute("""
            SELECT 
                table,
                formatReadableSize(sum(bytes_on_disk)) as size,
                sum(rows) as rows,
                sum(data_compressed_bytes) as compressed,
                sum(data_uncompressed_bytes) as uncompressed
            FROM system.parts
            WHERE database = ? AND table = ? AND active = 1
            GROUP BY table
        """, parameters=[self.database, table])
        
        if result.result_rows:
            row = result.result_rows[0]
            return {
                "table": row[0],
                "size": row[1],
                "rows": row[2],
                "compressed_bytes": row[3],
                "uncompressed_bytes": row[4],
            }
        return {}
    
    # ==================== Data Operations ====================
    
    async def insert_data(
        self,
        table: str,
        data: List[Dict[str, Any]],
        column_names: List[str] = None,
    ) -> int:
        """Insert data from list of dicts."""
        if not data:
            return 0
        
        if column_names is None:
            column_names = list(data[0].keys())
        
        values = [tuple(row[col] for col in column_names) for row in data]
        return await self.insert(table, values, column_names)
    
    async def insert_batch(
        self,
        table: str,
        data: List[Dict[str, Any]],
        batch_size: int = 10000,
    ) -> int:
        """Insert data in batches."""
        total = 0
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            total += await self.insert_data(table, batch)
        return total
    
    async def select(
        self,
        table: str,
        columns: List[str] = None,
        where: str = "",
        limit: int = None,
        order_by: str = "",
        sample: float = None,
    ) -> List[Dict[str, Any]]:
        """Select data from table."""
        cols = "*" if not columns else ", ".join(columns)
        query = f"SELECT {cols} FROM {table}"
        
        if where:
            query += f" WHERE {where}"
        if order_by:
            query += f" ORDER BY {order_by}"
        if sample:
            query += f" SAMPLE {sample}"
        if limit:
            query += f" LIMIT {limit}"
        
        result = await self.execute(query, with_column_names=True)
        return result.named_results()
    
    # ==================== Aggregation & Analytics ====================
    
    async def aggregate(
        self,
        table: str,
        metrics: List[str],
        group_by: List[str] = None,
        where: str = "",
        having: str = "",
        order_by: str = "",
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        """Execute aggregation query."""
        metrics_sql = ", ".join(metrics)
        group_by_sql = f"GROUP BY {', '.join(group_by)}" if group_by else ""
        where_sql = f"WHERE {where}" if where else ""
        having_sql = f"HAVING {having}" if having else ""
        order_by_sql = f"ORDER BY {order_by}" if order_by else ""
        limit_sql = f"LIMIT {limit}" if limit else ""
        
        query = f"""
            SELECT {metrics_sql}
            FROM {table}
            {where_sql}
            {group_by_sql}
            {having_sql}
            {order_by_sql}
            {limit_sql}
        """
        
        result = await self.execute(query.strip(), with_column_names=True)
        return result.named_results()
    
    async def time_series_aggregation(
        self,
        table: str,
        time_column: str,
        metrics: List[str],
        interval: str = "1h",
        where: str = "",
        fill_gaps: bool = True,
    ) -> List[Dict[str, Any]]:
        """Time-series aggregation with automatic bucketing."""
        interval_map = {
            "1s": "toStartOfSecond",
            "1m": "toStartOfMinute",
            "5m": "toStartOfFiveMinute",
            "15m": "toStartOfFifteenMinutes",
            "1h": "toStartOfHour",
            "1d": "toStartOfDay",
            "1w": "toStartOfWeek",
            "1M": "toStartOfMonth",
        }
        
        bucket_func = interval_map.get(interval, "toStartOfHour")
        
        metrics_sql = ", ".join([
            f"{m}({m}) as {m}" if not "(" in m else m
            for m in metrics
        ])
        
        query = f"""
            SELECT 
                {bucket_func}({time_column}) as bucket,
                {metrics_sql}
            FROM {table}
            {'WHERE ' + where if where else ''}
            GROUP BY bucket
            ORDER BY bucket
        """
        
        result = await self.execute(query.strip(), with_column_names=True)
        return result.named_results()
    
    async def percentile(
        self,
        table: str,
        column: str,
        percentiles: List[float],
        where: str = "",
    ) -> Dict[float, float]:
        """Calculate percentiles."""
        if not percentiles:
            return {}
        
        percents = ", ".join(str(p) for p in percentiles)
        query = f"""
            SELECT 
                quantiles({percents})({column}) as percentiles
            FROM {table}
            {'WHERE ' + where if where else ''}
        """
        
        result = await self.execute(query.strip(), with_column_names=True)
        if result.result_rows:
            perc_values = result.result_rows[0][0]
            return dict(zip(percentiles, perc_values))
        return {}
    
    async def top_k(
        self,
        table: str,
        column: str,
        k: int = 10,
        where: str = "",
        weight_column: str = None,
    ) -> List[Dict[str, Any]]:
        """Get top K values."""
        weight_clause = f", {weight_column}" if weight_column else ""
        query = f"""
            SELECT {column}, count(){weight_clause} as cnt
            FROM {table}
            {'WHERE ' + where if where else ''}
            GROUP BY {column}
            ORDER BY cnt DESC
            LIMIT {k}
        """
        
        result = await self.execute(query.strip(), with_column_names=True)
        return result.named_results()
    
    # ==================== Materialized Views ====================
    
    async def create_materialized_view(
        self,
        name: str,
        target_table: str,
        source_table: str,
        select_query: str,
        engine: ClickHouseEngine = ClickHouseEngine.MERGE_TREE,
        order_by: List[str] = None,
        partition_by: str = "",
    ) -> bool:
        """Create materialized view."""
        order_clause = f"ORDER BY ({', '.join(order_by)})" if order_by else ""
        partition_clause = f"PARTITION BY {partition_by}" if partition_by else ""
        
        query = f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS {name}
            ENGINE = {engine.value}()
            {partition_clause}
            {order_clause}
            AS {select_query}
            FROM {source_table}
            TO {target_table}
        """
        
        await self.execute(query.strip())
        return True
    
    async def drop_materialized_view(self, name: str) -> bool:
        """Drop materialized view."""
        await self.execute(f"DROP VIEW IF EXISTS {name}")
        return True
    
    # ==================== Kafka Engine Tables ====================
    
    async def create_kafka_table(
        self,
        table_name: str,
        columns: List[TableColumn],
        kafka_broker_list: str,
        kafka_topic_list: str,
        kafka_group_name: str,
        kafka_format: str = "JSONEachRow",
        kafka_schema: str = "",
        kafka_num_consumers: int = 1,
        kafka_max_block_size: int = 1048576,
        kafka_poll_timeout_ms: int = 1000,
    ) -> bool:
        """Create Kafka engine table for streaming ingestion."""
        columns_sql = ",\n    ".join([
            f"`{col.name}` {col.type}" + 
            (f" Nullable" if col.nullable else "") + 
            (f" DEFAULT {col.default}" if col.default else "") + 
            (f" CODEC({col.codec.value})" if col.codec != CompressionCodec.NONE else "")
            for col in columns
        ])
        
        settings = [
            f"kafka_broker_list = '{kafka_broker_list}'",
            f"kafka_topic_list = '{kafka_topic_list}'",
            f"kafka_group_name = '{kafka_group_name}'",
            f"kafka_format = '{kafka_format}'",
            f"kafka_num_consumers = {kafka_num_consumers}",
            f"kafka_max_block_size = {kafka_max_block_size}",
            f"kafka_poll_timeout_ms = {kafka_poll_timeout_ms}",
        ]
        
        if kafka_schema:
            settings.append(f"kafka_schema = '{kafka_schema}'")
        
        settings_sql = ",\n    ".join(settings)
        
        query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {columns_sql}
            ) ENGINE = Kafka()
            SETTINGS
                {settings_sql}
        """
        
        await self.execute(query.strip())
        return True
    
    # ==================== Vector Search ====================
    
    async def create_vector_index(
        self,
        table: str,
        column: str,
        index_name: str = None,
        index_type: str = "ANNOY",
        metric: str = "L2Distance",
        params: Dict[str, Any] = None,
    ) -> bool:
        """Create vector search index (ANN)."""
        name = index_name or f"idx_{table}_{column}_vector"
        params = params or {}
        
        if index_type == "ANNOY":
            n_trees = params.get("n_trees", 100)
            query = f"""
                ALTER TABLE {table} 
                ADD VECTOR INDEX {name} {column} TYPE ANNOY({n_trees})
            """
        elif index_type == "HNSW":
            m = params.get("m", 16)
            ef_construction = params.get("ef_construction", 200)
            query = f"""
                ALTER TABLE {table} 
                ADD VECTOR INDEX {name} {column} TYPE HNSW({m}, {ef_construction})
            """
        elif index_type == "IVF":
            n_lists = params.get("n_lists", 100)
            query = f"""
                ALTER TABLE {table} 
                ADD VECTOR INDEX {name} {column} TYPE IVF({n_lists})
            """
        else:
            raise ValueError(f"Unknown index type: {index_type}")
        
        await self.execute(query.strip())
        return True
    
    async def vector_search(
        self,
        table: str,
        column: str,
        query_vector: List[float],
        k: int = 10,
        distance_metric: str = "L2Distance",
        filter: str = "",
    ) -> List[Dict[str, Any]]:
        """Vector similarity search."""
        distance_func = distance_metric
        query = f"""
            SELECT *, {distance_func}({column}, ?) as distance
            FROM {table}
            {'WHERE ' + filter if filter else ''}
            ORDER BY distance ASC
            LIMIT ?
        """
        
        result = await self.execute(query, parameters=[query_vector, k], with_column_names=True)
        return result.named_results()
    
    # ==================== Time-Series ====================
    
    async def downsample(
        self,
        source_table: str,
        target_table: str,
        time_column: str,
        interval: str,
        metrics: List[str],
        where: str = "",
    ) -> bool:
        """Create downsampled table with continuous aggregation."""
        # Create target table if not exists
        # This would typically use a materialized view with continuous aggregation
        pass
    
    async def create_continuous_aggregation(
        self,
        view_name: str,
        source_table: str,
        time_column: str,
        bucket_interval: str,
        metrics: Dict[str, str],  # metric_name -> aggregation_function
        where: str = "",
    ) -> bool:
        """Create continuous aggregation view."""
        metrics_sql = ", ".join([
            f"{func}({col}) as {alias}" 
            for alias, (col, func) in metrics.items()
        ])
        
        bucket_func = {
            "1s": "toStartOfSecond",
            "1m": "toStartOfMinute",
            "5m": "toStartOfFiveMinute",
            "15m": "toStartOfFifteenMinutes",
            "1h": "toStartOfHour",
            "1d": "toStartOfDay",
            "1w": "toStartOfWeek",
            "1M": "toStartOfMonth",
        }.get(bucket_interval, "toStartOfHour")
        
        query = f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name}
            ENGINE = SummingMergeTree()
            PARTITION BY toYYYYMM({time_column})
            ORDER BY ({time_column})
            AS SELECT 
                {bucket_func}({time_column}) as {time_column},
                {metrics_sql}
            FROM {source_table}
            {'WHERE ' + where if where else ''}
            GROUP BY {time_column}
        """
        
        await self.execute(query.strip())
        return True
    
    # ==================== Data Export/Import ====================
    
    async def export_to_file(
        self,
        table: str,
        file_path: str,
        format: str = "Parquet",
        where: str = "",
    ) -> bool:
        """Export table to file."""
        query = f"""
            SELECT * FROM {table}
            {'WHERE ' + where if where else ''}
            INTO OUTFILE '{file_path}'
            FORMAT {format}
        """
        await self.execute(query)
        return True
    
    async def import_from_file(
        self,
        table: str,
        file_path: str,
        format: str = "Parquet",
        columns: List[str] = None,
    ) -> bool:
        """Import data from file."""
        cols = f"({', '.join(columns)})" if columns else ""
        query = f"""
            INSERT INTO {table} {cols}
            FROM INFILE '{file_path}'
            FORMAT {format}
        """
        await self.execute(query)
        return True
    
    async def export_to_s3(
        self,
        table: str,
        s3_url: str,
        format: str = "Parquet",
        where: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
    ) -> bool:
        """Export to S3."""
        query = f"""
            SELECT * FROM {table}
            {'WHERE ' + where if where else ''}
            INTO OUTFILE '{s3_url}'
            FORMAT {format}
            SETTINGS s3_access_key_id = '{access_key_id}',
                     s3_secret_access_key = '{secret_access_key}'
        """
        await self.execute(query)
        return True
    
    # ==================== System Operations ====================
    
    async def get_server_info(self) -> Dict[str, Any]:
        """Get server information."""
        result = await self.execute("SELECT version(), serverDisplayName()")
        return {"version": result.result_rows[0][0], "display_name": result.result_rows[0][1]}
    
    async def get_tables(self, database: str = None) -> List[Dict]:
        """Get list of tables."""
        db = database or self.database
        result = await self.execute(
            "SELECT name, engine, total_rows, total_bytes FROM system.tables WHERE database = ?",
            parameters=[db],
        )
        return result.named_results()
    
    async def get_table_info(self, table: str) -> Dict:
        """Get detailed table information."""
        result = await self.execute(
            "SELECT * FROM system.tables WHERE database = ? AND name = ?",
            parameters=[self.database, table],
        )
        return result.named_results()[0] if result.result_rows else {}
    
    async def get_columns(self, table: str) -> List[Dict]:
        """Get table columns."""
        result = await self.execute(
            "SELECT name, type, default_kind, default_expression, comment FROM system.columns WHERE database = ? AND table = ?",
            parameters=[self.database, table],
        )
        return result.named_results()
    
    async def optimize_table(self, table: str, final: bool = False, partition: str = None) -> bool:
        """Optimize table (merge parts)."""
        query = f"OPTIMIZE TABLE {table}"
        if final:
            query += " FINAL"
        if partition:
            query += f" PARTITION {partition}"
        await self.execute(query)
        return True
    
    async def get_mutation_status(self, table: str) -> List[Dict]:
        """Get mutation status for table."""
        result = await self.execute(
            "SELECT * FROM system.mutations WHERE database = ? AND table = ? AND is_done = 0",
            parameters=[self.database, table],
        )
        return result.named_results()
    
    async def get_parts_info(self, table: str) -> List[Dict]:
        """Get parts information for table."""
        result = await self.execute(
            """
            SELECT partition, name, rows, bytes_on_disk, 
                   data_compressed_bytes, data_uncompressed_bytes,
                   compression_ratio, level, active
            FROM system.parts
            WHERE database = ? AND table = ? AND active = 1
            ORDER BY partition, name
            """,
            parameters=[self.database, table],
        )
        return result.named_results()
    
    async def get_merges_info(self) -> List[Dict]:
        """Get current merge operations."""
        result = await self.execute("""
            SELECT database, table, elapsed, progress_num_parts, total_num_parts,
                   bytes_read, bytes_written, rows_read, rows_written
            FROM system.merges
            WHERE is_cancelled = 0
        """)
        return result.named_results()
    
    async def get_query_log(self, limit: int = 100) -> List[Dict]:
        """Get recent query log."""
        result = await self.execute(f"""
            SELECT query, query_duration_ms, read_rows, read_bytes,
                   written_rows, written_bytes, result_rows, result_bytes,
                   memory_usage, query_start_time, user, query_id
            FROM system.query_log
            WHERE event_date >= today() - 1
            ORDER BY event_time DESC
            LIMIT {limit}
        """)
        return result.named_results()
    
    async def kill_query(self, query_id: str) -> bool:
        """Kill running query."""
        await self.execute(f"KILL QUERY WHERE query_id = '{query_id}'")
        return True


# ==================== Distributed ClickHouse ====================

class DistributedClickHouse:
    """Distributed ClickHouse cluster management."""
    
    def __init__(self, cluster_name: str, shards: List[ClickHouseAnalytics]):
        self.cluster_name = cluster_name
        self.shards = shards
    
    async def execute_on_all(self, query: str, parameters: Dict = None) -> Dict[str, QueryResult]:
        """Execute query on all shards."""
        results = {}
        for shard in self.shards:
            try:
                results[shard.database] = await shard.execute(query, parameters)
            except Exception as e:
                results[shard.database] = {"error": str(e)}
        return results
    
    async def insert_distributed(
        self,
        table: str,
        data: List[Dict[str, Any]],
        shard_key: str = None,
    ) -> int:
        """Insert data with automatic shard routing."""
        if not self.shards:
            raise ValueError("No shards configured")
        
        # Simple round-robin or key-based routing
        total = 0
        for shard in self.shards:
            total += await shard.insert_batch(shard.database, [data])
        return total


# ==================== Global Instance ====================

_clickhouse_analytics: Optional[ClickHouseAnalytics] = None


def get_clickhouse_analytics() -> ClickHouseAnalytics:
    """Get global ClickHouse analytics instance."""
    global _clickhouse_analytics
    if _clickhouse_analytics is None:
        _clickhouse_analytics = ClickHouseAnalytics(
            host=getattr(settings, 'CLICKHOUSE_HOST', 'localhost'),
            port=getattr(settings, 'CLICKHOUSE_PORT', 8123),
            username=getattr(settings, 'CLICKHOUSE_USER', 'default'),
            password=getattr(settings, 'CLICKHOUSE_PASSWORD', ''),
            database=getattr(settings, 'CLICKHOUSE_DATABASE', 'vcos_analytics'),
        )
    return _clickhouse_analytics


async def init_clickhouse_analytics(
    host: str = None,
    port: int = None,
    username: str = None,
    password: str = None,
    database: str = None,
    secure: bool = False,
) -> ClickHouseAnalytics:
    """Initialize ClickHouse analytics."""
    global _clickhouse_analytics
    _clickhouse_analytics = ClickHouseAnalytics(
        host=host or getattr(settings, 'CLICKHOUSE_HOST', 'localhost'),
        port=port or getattr(settings, 'CLICKHOUSE_PORT', 8123),
        username=username or getattr(settings, 'CLICKHOUSE_USER', 'default'),
        password=password or getattr(settings, 'CLICKHOUSE_PASSWORD', ''),
        database=database or getattr(settings, 'CLICKHOUSE_DATABASE', 'vcos_analytics'),
        secure=secure or getattr(settings, 'CLICKHOUSE_SECURE', False),
    )
    await _clickhouse_analytics.initialize()
    return _clickhouse_analytics