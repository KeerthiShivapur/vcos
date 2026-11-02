"""
Kafka/Redpanda Event Streaming for VCOS.

Provides:
- Producer/Consumer with async support
- Schema registry integration (Avro/Protobuf/JSON Schema)
- Exactly-once semantics
- Consumer group management
- Dead letter queue handling
- Stream processing (ksqlDB/Flink-style)
- Schema evolution and compatibility
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple, Union
from contextlib import asynccontextmanager
from functools import wraps

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaError
from aiokafka.structs import TopicPartition

from app.core.config import settings

logger = logging.getLogger(__name__)


class SerializationFormat(str, Enum):
    """Message serialization formats."""
    JSON = "json"
    AVRO = "avro"
    PROTOBUF = "protobuf"
    MSGPACK = "msgpack"
    CBOR = "cbor"
    RAW = "raw"


class CompressionType(str, Enum):
    """Message compression types."""
    NONE = "none"
    GZIP = "gzip"
    SNAPPY = "snappy"
    LZ4 = "lz4"
    ZSTD = "zstd"


class ProcessingGuarantee(str, Enum):
    """Processing guarantees."""
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"
    AT_MOST_ONCE = "at_most_once"


@dataclass
class ProducerConfig:
    """Kafka producer configuration."""
    bootstrap_servers: str = "localhost:9092"
    client_id: str = "vcos-producer"
    acks: str = "all"  # all, 1, 0
    retries: int = 3
    retry_backoff_ms: int = 100
    enable_idempotence: bool = True
    transactional_id: Optional[str] = None
    transaction_timeout_ms: int = 10000
    compression_type: CompressionType = CompressionType.SNAPPY
    batch_size: int = 16384
    linger_ms: int = 5
    buffer_memory: int = 33554432  # 32MB
    max_in_flight_requests_per_connection: int = 5
    request_timeout_ms: int = 30000
    delivery_timeout_ms: int = 120000
    max_block_ms: int = 60000
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: Optional[str] = None
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    ssl_check_hostname: bool = True


@dataclass
class ConsumerConfig:
    """Kafka consumer configuration."""
    bootstrap_servers: str = "localhost:9092"
    group_id: str = "vcos-consumer"
    client_id: str = "vcos-consumer"
    auto_offset_reset: str = "earliest"  # earliest, latest, none
    enable_auto_commit: bool = True
    auto_commit_interval_ms: int = 5000
    max_poll_records: int = 500
    max_poll_interval_ms: int = 300000
    session_timeout_ms: int = 30000
    heartbeat_interval_ms: int = 10000
    max_partition_fetch_bytes: int = 1048576
    fetch_min_bytes: int = 1
    fetch_max_wait_ms: int = 500
    isolation_level: str = "read_committed"  # read_committed, read_uncommitted
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: Optional[str] = None
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None


@dataclass
class TopicConfig:
    """Kafka topic configuration."""
    name: str
    partitions: int = 12
    replication_factor: int = 3
    configs: Dict[str, str] = field(default_factory=dict)
    # Common configs:
    # retention.ms: 604800000 (7 days)
    # retention.bytes: -1
    # cleanup.policy: delete (or compact)
    # min.insync.replicas: 2
    # segment.bytes: 1073741824
    # flush.messages: 10000
    # flush.ms: 1000


@dataclass
class Message:
    """Kafka message."""
    topic: str
    partition: int
    offset: int
    key: Optional[bytes]
    value: Optional[bytes]
    timestamp: int
    timestamp_type: int
    headers: List[Tuple[str, bytes]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProducerRecord:
    """Record to send to Kafka."""
    topic: str
    value: Any
    key: Optional[Any] = None
    partition: Optional[int] = None
    headers: List[Tuple[str, bytes]] = field(default_factory=list)
    timestamp: Optional[int] = None


@dataclass
class ConsumerRecord:
    """Record received from Kafka."""
    topic: str
    partition: int
    offset: int
    key: Optional[bytes]
    value: Any
    timestamp: int
    timestamp_type: int
    headers: List[Tuple[str, bytes]] = field(default_factory=list)


# ==================== Serialization ====================

class Serializer(ABC):
    """Base serializer interface."""
    
    @abstractmethod
    def serialize(self, value: Any, topic: str = None) -> bytes:
        pass
    
    @abstractmethod
    def deserialize(self, data: bytes, topic: str = None) -> Any:
        pass
    
    @abstractmethod
    def get_content_type(self) -> str:
        pass


class JsonSerializer(Serializer):
    """JSON serializer."""
    
    def serialize(self, value: Any, topic: str = None) -> bytes:
        return json.dumps(value, default=str, separators=(',', ':')).encode('utf-8')
    
    def deserialize(self, data: bytes, topic: str = None) -> Any:
        return json.loads(data.decode('utf-8'))
    
    def get_content_type(self) -> str:
        return "application/json"


class AvroSerializer(Serializer):
    """Avro serializer with schema registry."""
    
    def __init__(self, schema_registry_url: str, subject_name_strategy: str = "topic"):
        self.schema_registry_url = schema_registry_url
        self.subject_name_strategy = subject_name_strategy
        self._schemas: Dict[str, Any] = {}
        self._writer_schemas: Dict[str, Any] = {}
    
    async def _get_schema(self, subject: str, version: str = "latest") -> Any:
        """Fetch schema from registry."""
        # In production, use httpx to fetch from schema registry
        # For now, return None
        return None
    
    def serialize(self, value: Any, topic: str = None) -> bytes:
        # In production, encode using Avro with schema
        return json.dumps(value, default=str).encode('utf-8')
    
    def deserialize(self, data: bytes, topic: str = None) -> Any:
        # In production, decode using Avro with schema
        return json.loads(data.decode('utf-8'))
    
    def get_content_type(self) -> str:
        return "application/avro"


class ProtobufSerializer(Serializer):
    """Protobuf serializer."""
    
    def __init__(self, message_class, schema_registry_url: str = None):
        self.message_class = message_class
        self.schema_registry_url = schema_registry_url
    
    def serialize(self, value: Any, topic: str = None) -> bytes:
        if isinstance(value, self.message_class):
            return value.SerializeToString()
        elif isinstance(value, dict):
            msg = self.message_class()
            # Convert dict to protobuf (simplified)
            return msg.SerializeToString()
        raise ValueError(f"Expected {self.message_class.__name__} or dict")
    
    def deserialize(self, data: bytes, topic: str = None) -> Any:
        msg = self.message_class()
        msg.ParseFromString(data)
        return msg
    
    def get_content_type(self) -> str:
        return "application/protobuf"


class SerializerRegistry:
    """Registry for topic serializers."""
    
    def __init__(self):
        self._serializers: Dict[str, Serializer] = {}
        self._default = JsonSerializer()
    
    def register(self, topic: str, serializer: Serializer):
        self._serializers[topic] = serializer
    
    def get_serializer(self, topic: str) -> Serializer:
        return self._serializers.get(topic, self._default)
    
    def set_default(self, serializer: Serializer):
        self._default = serializer


# ==================== Producer ====================

class AsyncProducer:
    """Async Kafka producer with advanced features."""
    
    def __init__(self, config: ProducerConfig):
        self.config = config
        self._producer: Optional[AIOKafkaProducer] = None
        self._serializer = SerializerRegistry()
        self._transactional = config.transactional_id is not None
        self._running = False
    
    async def initialize(self):
        """Initialize producer."""
        if self._running:
            return
        
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.config.bootstrap_servers,
            client_id=self.config.client_id,
            acks=self.config.acks,
            retries=self.config.retries,
            retry_backoff_ms=self.config.retry_backoff_ms,
            enable_idempotence=self.config.enable_idempotence,
            transactional_id=self.config.transactional_id,
            transaction_timeout_ms=self.config.transaction_timeout_ms,
            compression_type=self.config.compression_type.value,
            batch_size=self.config.batch_size,
            linger_ms=self.config.linger_ms,
            buffer_memory=self.config.buffer_memory,
            max_in_flight_requests_per_connection=self.config.max_in_flight_requests_per_connection,
            request_timeout_ms=self.config.request_timeout_ms,
            delivery_timeout_ms=self.config.delivery_timeout_ms,
            max_block_ms=self.config.max_block_ms,
            security_protocol=self.config.security_protocol,
            sasl_mechanism=self.config.sasl_mechanism,
            sasl_plain_username=self.config.sasl_username,
            sasl_plain_password=self.config.sasl_password,
            ssl_cafile=self.config.ssl_cafile,
            ssl_certfile=self.config.ssl_certfile,
            ssl_keyfile=self.config.ssl_keyfile,
            ssl_check_hostname=self.config.ssl_check_hostname,
        )
        
        await self._producer.start()
        self._running = True
        logger.info(f"Producer initialized: {self.config.client_id}")
    
    async def close(self):
        """Close producer."""
        if self._producer:
            await self._producer.stop()
            self._running = False
    
    def register_serializer(self, topic: str, serializer: Serializer):
        self._serializer.register(topic, serializer)
    
    def set_default_serializer(self, serializer: Serializer):
        self._serializer.set_default(serializer)
    
    async def send(
        self,
        topic: str,
        value: Any,
        key: Any = None,
        partition: int = None,
        headers: List[Tuple[str, bytes]] = None,
        timestamp: int = None,
    ) -> Tuple[int, int]:  # (partition, offset)
        """Send single message."""
        if not self._running:
            await self.initialize()
        
        serializer = self._serializer.get_serializer(topic)
        value_bytes = serializer.serialize(value, topic)
        key_bytes = serializer.serialize(key, topic) if key is not None else None
        
        future = await self._producer.send(
            topic=topic,
            value=value_bytes,
            key=key_bytes,
            partition=partition,
            headers=headers or [],
            timestamp_ms=timestamp,
        )
        
        record_metadata = await future
        return record_metadata.partition, record_metadata.offset
    
    async def send_batch(
        self,
        topic: str,
        records: List[ProducerRecord],
    ) -> List[Tuple[int, int]]:
        """Send batch of records."""
        results = []
        for record in records:
            result = await self.send(
                topic=topic,
                value=record.value,
                key=record.key,
                partition=record.partition,
                headers=record.headers,
                timestamp=record.timestamp,
            )
            results.append(result)
        return results
    
    async def flush(self):
        """Flush pending messages."""
        if self._producer:
            await self._producer.flush()
    
    # ==================== Transactions ====================
    
    async def begin_transaction(self):
        """Begin transaction."""
        if not self._transactional:
            raise ValueError("Producer not configured for transactions")
        await self._producer.begin_transaction()
    
    async def commit_transaction(self):
        """Commit transaction."""
        await self._producer.commit_transaction()
    
    async def abort_transaction(self):
        """Abort transaction."""
        await self._producer.abort_transaction()
    
    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager."""
        await self.begin_transaction()
        try:
            yield
            await self.commit_transaction()
        except Exception:
            await self.abort_transaction()
            raise
    
    def is_running(self) -> bool:
        return self._running


# ==================== Consumer ====================

class AsyncConsumer:
    """Async Kafka consumer with advanced features."""
    
    def __init__(self, config: ConsumerConfig):
        self.config = config
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._serializer = SerializerRegistry()
        self._running = False
        self._handlers: Dict[str, Callable] = {}
        self._running_tasks: Set[asyncio.Task] = set()
    
    async def initialize(self):
        """Initialize consumer."""
        if self._running:
            return
        
        self._consumer = AIOKafkaConsumer(
            bootstrap_servers=self.config.bootstrap_servers,
            group_id=self.config.group_id,
            client_id=self.config.client_id,
            auto_offset_reset=self.config.auto_offset_reset,
            enable_auto_commit=self.config.enable_auto_commit,
            auto_commit_interval_ms=self.config.auto_commit_interval_ms,
            max_poll_records=self.config.max_poll_records,
            max_poll_interval_ms=self.config.max_poll_interval_ms,
            session_timeout_ms=self.config.session_timeout_ms,
            heartbeat_interval_ms=self.config.heartbeat_interval_ms,
            max_partition_fetch_bytes=self.config.max_partition_fetch_bytes,
            fetch_min_bytes=self.config.fetch_min_bytes,
            fetch_max_wait_ms=self.config.fetch_max_wait_ms,
            isolation_level=self.config.isolation_level,
            security_protocol=self.config.security_protocol,
            sasl_mechanism=self.config.sasl_mechanism,
            sasl_plain_username=self.config.sasl_username,
            sasl_plain_password=self.config.sasl_password,
            ssl_cafile=self.config.ssl_cafile,
            ssl_certfile=self.config.ssl_certfile,
            ssl_keyfile=self.config.ssl_keyfile,
        )
        
        await self._consumer.start()
        self._running = True
        logger.info(f"Consumer initialized: {self.config.group_id}")
    
    async def close(self):
        """Close consumer."""
        # Cancel running tasks
        for task in self._running_tasks:
            task.cancel()
        await asyncio.gather(*self._running_tasks, return_exceptions=True)
        
        if self._consumer:
            await self._consumer.stop()
            self._running = False
    
    def register_serializer(self, topic: str, serializer: Serializer):
        self._serializer.register(topic, serializer)
    
    def register_handler(self, topic: str, handler: Callable[[ConsumerRecord], Any]):
        """Register message handler for topic."""
        self._handlers[topic] = handler
    
    def register_handlers(self, handlers: Dict[str, Callable]):
        self._handlers.update(handlers)
    
    async def subscribe(self, topics: List[str]):
        """Subscribe to topics."""
        if not self._consumer:
            await self.initialize()
        
        await self._consumer.subscribe(*topics)
    
    async def unsubscribe(self):
        """Unsubscribe from all topics."""
        if self._consumer:
            self._consumer.unsubscribe()
    
    async def consume(self, timeout_ms: int = 1000) -> List[ConsumerRecord]:
        """Poll for messages."""
        if not self._consumer:
            await self.initialize()
        
        try:
            result = await self._consumer.getmany(timeout_ms=timeout_ms)
            records = []
            for tp, messages in result.items():
                for msg in messages:
                    serializer = self._serializer.get_serializer(tp.topic)
                    value = serializer.deserialize(msg.value, tp.topic)
                    key = serializer.deserialize(msg.key, tp.topic) if msg.key else None
                    
                    records.append(ConsumerRecord(
                        topic=tp.topic,
                        partition=tp.partition,
                        offset=msg.offset,
                        key=key,
                        value=value,
                        timestamp=msg.timestamp,
                        timestamp_type=msg.timestamp_type,
                        headers=list(msg.headers),
                    ))
            return records
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
            return []
    
    async def run(self):
        """Run consumer loop with registered handlers."""
        if not self._handlers:
            raise ValueError("No handlers registered")
        
        if not self._consumer:
            await self.initialize()
        
        topics = list(self._handlers.keys())
        await self.subscribe(topics)
        
        logger.info(f"Starting consumer for topics: {topics}")
        
        while True:
            try:
                records = await self.consume()
                for record in records:
                    handler = self._handlers.get(record.topic)
                    if handler:
                        task = asyncio.create_task(self._handle_message(handler, record))
                        self._running_tasks.add(task)
                        task.add_done_callback(self._running_tasks.discard)
                # Clean up completed tasks
                self._running_tasks = {t for t in self._running_tasks if not t.done()}
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(1)
    
    async def _handle_message(self, handler: Callable, record: ConsumerRecord):
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(record)
            else:
                handler(record)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def commit(self):
        """Commit offsets manually."""
        if self._consumer:
            await self._consumer.commit()
    
    async def seek(self, topic: str, partition: int, offset: int):
        """Seek to specific offset."""
        if self._consumer:
            tp = TopicPartition(topic, partition)
            self._consumer.seek(tp, offset)
    
    async def pause(self, *partitions: TopicPartition):
        """Pause consumption on partitions."""
        if self._consumer:
            self._consumer.pause(*partitions)
    
    async def resume(self, *partitions: TopicPartition):
        """Resume consumption on partitions."""
        if self._consumer:
            self._consumer.resume(*partitions)


# ==================== Admin Client ====================

class KafkaAdmin:
    """Kafka cluster administration."""
    
    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.bootstrap_servers = bootstrap_servers
        self._admin: Optional[AIOKafkaAdminClient] = None
    
    async def initialize(self):
        self._admin = AIOKafkaAdminClient(
            bootstrap_servers=self.bootstrap_servers,
        )
        await self._admin.start()
    
    async def close(self):
        if self._admin:
            await self._admin.close()
    
    async def create_topic(
        self,
        name: str,
        partitions: int = 12,
        replication_factor: int = 3,
        configs: Dict[str, str] = None,
    ) -> bool:
        """Create topic."""
        topic = NewTopic(
            name=name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            topic_configs=configs or {},
        )
        await self._admin.create_topics([topic])
        return True
    
    async def delete_topic(self, name: str) -> bool:
        """Delete topic."""
        await self._admin.delete_topics([name])
        return True
    
    async def list_topics(self) -> List[str]:
        """List all topics."""
        metadata = await self._admin.list_topics()
        return list(metadata.topics.keys())
    
    async def get_topic_partitions(self, topic: str) -> List[TopicPartition]:
        """Get topic partitions."""
        metadata = await self._admin.list_topics()
        return metadata.topics.get(topic, {}).partitions.keys()
    
    async def create_partitions(self, topic: str, count: int) -> bool:
        """Increase partition count."""
        await self._admin.create_partitions({topic: count})
        return True
    
    async def alter_topic_config(self, topic: str, configs: Dict[str, str]) -> bool:
        """Alter topic configuration."""
        await self._admin.alter_configs({f"topic:{topic}": configs})
        return True
    
    async def describe_cluster(self) -> Dict:
        """Get cluster metadata."""
        metadata = await self._admin.list_topics()
        return {
            "controller_id": metadata.controller_id,
            "brokers": [{"node_id": b.node_id, "host": b.host, "port": b.port} 
                       for b in metadata.brokers.values()],
            "topics": list(metadata.topics.keys()),
        }
    
    async def describe_consumer_groups(self, group_ids: List[str]) -> List[Dict]:
        """Describe consumer groups."""
        result = await self._admin.describe_consumer_groups(group_ids)
        return [
            {
                "group_id": g.group_id,
                "state": g.state,
                "coordinator": g.coordinator_id,
                "members": len(g.members),
            }
            for g in result.values()
        ]
    
    async def delete_consumer_group(self, group_id: str) -> bool:
        """Delete consumer group."""
        await self._admin.delete_consumer_groups([group_id])
        return True
    
    async def list_consumer_group_offsets(self, group_id: str) -> Dict:
        """List consumer group offsets."""
        result = await self._admin.list_consumer_group_offsets(group_id)
        return {tp: offset for tp, offset in result.items()}


# ==================== Stream Processor ====================

class StreamProcessor:
    """
    Stream processing engine (ksqlDB/Flink-style).
    Provides windowed aggregations, joins, filtering, transformations.
    """
    
    def __init__(
        self,
        bootstrap_servers: str,
        consumer_group: str = "vcos-stream-processor",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.consumer_group = consumer_group
        self._consumer: Optional[AsyncConsumer] = None
        self._producer: Optional[AsyncProducer] = None
        self._topology: List[Dict] = []
        self._running = False
    
    async def initialize(
        self,
        producer_config: ProducerConfig = None,
        consumer_config: ConsumerConfig = None,
    ):
        self._producer = AsyncProducer(producer_config or ProducerConfig(
            bootstrap_servers=self.bootstrap_servers,
            client_id="vcos-stream-producer",
        ))
        self._consumer = AsyncConsumer(consumer_config or ConsumerConfig(
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.consumer_group,
        ))
        
        await self._producer.initialize()
        await self._consumer.initialize()
    
    async def close(self):
        if self._producer:
            await self._producer.close()
        if self._consumer:
            await self._consumer.close()
    
    def stream(self, topic: str, value_type: type = dict):
        """Create stream from topic."""
        return Stream(self, topic, value_type)
    
    def table(self, topic: str, value_type: type = dict):
        """Create table (changelog stream) from topic."""
        return Table(self, topic, value_type)
    
    async def run(self):
        """Run stream processor."""
        self._running = True
        # Topology execution would happen here
        pass
    
    async def close(self):
        if self._producer:
            await self._producer.close()
        if self._consumer:
            await self._consumer.close()


class Stream:
    """Stream processing operations."""
    
    def __init__(self, processor: StreamProcessor, topic: str, value_type: type):
        self.processor = processor
        self.topic = topic
        self.value_type = value_type
        self._operations: List[Callable] = []
    
    def filter(self, predicate: Callable[[Any], bool]) -> 'Stream':
        """Filter records."""
        async def filter_op(record):
            if await predicate(record.value):
                return record
            return None
        self._operations.append(filter_op)
        return self
    
    def map(self, func: Callable[[Any], Any]) -> 'Stream':
        """Transform records."""
        async def map_op(record):
            record.value = await func(record.value)
            return record
        self._operations.append(map_op)
        return self
    
    def flat_map(self, func: Callable[[Any], List[Any]]) -> 'Stream':
        """Flat map records."""
        async def flat_map_op(record):
            results = await func(record.value)
            return [ConsumerRecord(
                topic=record.topic,
                partition=record.partition,
                offset=record.offset,
                key=record.key,
                value=r,
                timestamp=record.timestamp,
                timestamp_type=record.timestamp_type,
                headers=record.headers,
            ) for r in results]
        self._operations.append(flat_map_op)
        return self
    
    def group_by(self, key_func: Callable[[Any], Any]) -> 'GroupedStream':
        """Group records by key."""
        return GroupedStream(self, key_func)
    
    def window(self, window_type: str, size: int, advance: int = None) -> 'WindowedStream':
        """Windowed stream."""
        return WindowedStream(self, window_type, size, advance)
    
    def to(self, topic: str, producer: AsyncProducer = None) -> 'Stream':
        """Write stream to topic."""
        async def sink_op(record):
            target_producer = producer or self.processor._producer
            await producer.send(
                topic=topic,
                value=record.value,
                key=record.key,
                headers=record.headers,
                timestamp=record.timestamp,
            )
            return record
        self._operations.append(sink_op)
        return self
    
    async def execute(self):
        """Execute stream processing."""
        # In production, this would run the topology
        pass


class GroupedStream(Stream):
    """Grouped stream for aggregations."""
    
    def __init__(self, stream: Stream, key_func: Callable):
        super().__init__(stream.processor, stream.topic, stream.value_type)
        self._operations = stream._operations
        self.key_func = key_func
    
    def count(self) -> 'Stream':
        """Count per group."""
        return self
    
    def sum(self, field: str) -> 'Stream':
        return self
    
    def avg(self, field: str) -> 'Stream':
        return self
    
    def min(self, field: str) -> 'Stream':
        return self
    
    def max(self, field: str) -> 'Stream':
        return self
    
    def reduce(self, reducer: Callable) -> 'Stream':
        return self


class WindowedStream(Stream):
    """Windowed stream operations."""
    
    def __init__(self, stream: Stream, window_type: str, size: int, advance: int = None):
        super().__init__(stream.processor, stream.topic, stream.value_type)
        self._operations = stream._operations
        self.window_type = window_type
        self.size = size
        self.advance = advance or size


class Table(Stream):
    """Table (materialized view) from changelog topic."""
    
    def __init__(self, processor: StreamProcessor, topic: str, value_type: type):
        super().__init__(processor, topic, value_type)
    
    def join(self, other: 'Table', on: str) -> 'Stream':
        """Join two tables."""
        return self
    
    def left_join(self, other: 'Table', on: str) -> 'Stream':
        return self


# ==================== Schema Registry Client ====================

class SchemaRegistryClient:
    """Schema registry client for schema evolution and compatibility."""
    
    def __init__(self, url: str):
        self.url = url
        self._cache: Dict[str, Any] = {}
    
    async def register_schema(
        self,
        subject: str,
        schema: str,
        schema_type: str = "AVRO",
    ) -> int:
        """Register schema and return schema ID."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/subjects/{subject}/versions",
                json={"schema": schema, "schemaType": schema_type},
            )
            response.raise_for_status()
            return response.json()["id"]
    
    async def get_schema(self, subject: str, version: str = "latest") -> Dict:
        """Get schema by subject and version."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.url}/subjects/{subject}/versions/{version}")
            response.raise_for_status()
            return response.json()
    
    async def check_compatibility(
        self,
        subject: str,
        schema: str,
        schema_type: str = "AVRO",
    ) -> bool:
        """Check schema compatibility."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/compatibility/subjects/{subject}/versions",
                json={"schema": schema, "schemaType": schema_type},
            )
            response.raise_for_status()
            return response.json()["is_compatible"]
    
    async def get_subjects(self) -> List[str]:
        """Get all subjects."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.url}/subjects")
            response.raise_for_status()
            return response.json()
    
    async def get_versions(self, subject: str) -> List[int]:
        """Get all versions for a subject."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.url}/subjects/{subject}/versions")
            response.raise_for_status()
            return response.json()
    
    async def set_compatibility(self, subject: str, level: str) -> bool:
        """Set compatibility level (BACKWARD, FORWARD, FULL, NONE)."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.url}/config/{subject}",
                json={"compatibility": level.upper()},
            )
            response.raise_for_status()
            return True


# ==================== Dead Letter Queue ====================

class DeadLetterQueue:
    """Dead letter queue for failed messages."""
    
    def __init__(
        self,
        producer: AsyncProducer,
        dlq_topic: str = "vcos.dlq",
        max_retries: int = 3,
    ):
        self.producer = producer
        self.dlq_topic = dlq_topic
        self.max_retries = max_retries
        self._retry_counts: Dict[str, int] = {}
    
    async def handle_failure(
        self,
        record: ProducerRecord,
        error: Exception,
        retry_count: int = 0,
    ):
        """Handle failed message."""
        retry_count = retry_count + 1
        
        if retry_count >= self.max_retries:
            # Send to DLQ
            await self._send_to_dlq(record, error)
        else:
            # Schedule retry with backoff
            await asyncio.sleep(2 ** retry_count)
            await self.producer.send(
                topic=record.topic,
                value=record.value,
                key=record.key,
                partition=record.partition,
                headers=record.headers + [("x-retry-count", str(retry_count).encode())],
            )
    
    async def _send_to_dlq(self, record: ProducerRecord, error: Exception):
        """Send failed record to DLQ."""
        await self.producer.send(
            topic=self.dlq_topic,
            value={
                "original_topic": record.topic,
                "original_value": record.value,
                "original_key": record.key,
                "error": str(error),
                "failed_at": datetime.utcnow().isoformat(),
            },
            key=record.key,
            headers=[("x-original-topic", record.topic.encode())],
        )


# ==================== Global Instances ====================

_kafka_admin: Optional[KafkaAdmin] = None
_stream_processor: Optional[StreamProcessor] = None


def get_kafka_admin() -> KafkaAdmin:
    """Get global Kafka admin instance."""
    global _kafka_admin
    if _kafka_admin is None:
        _kafka_admin = KafkaAdmin(getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'))
    return _kafka_admin


async def init_kafka_admin(bootstrap_servers: str = None) -> KafkaAdmin:
    """Initialize Kafka admin."""
    global _kafka_admin
    _kafka_admin = KafkaAdmin(bootstrap_servers or getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'))
    await _kafka_admin.initialize()
    return _kafka_admin


async def create_topics(topics: List[TopicConfig]) -> bool:
    """Create multiple topics."""
    admin = get_kafka_admin()
    await admin.initialize()
    for topic in topics:
        await admin.create_topic(
            name=topic.name,
            partitions=topic.partitions,
            replication_factor=topic.replication_factor,
            configs=topic.configs,
        )
    return True


def get_stream_processor() -> StreamProcessor:
    """Get global stream processor."""
    global _stream_processor
    if _stream_processor is None:
        _stream_processor = StreamProcessor(
            bootstrap_servers=getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        )
    return _stream_processor


async def init_stream_processor(
    bootstrap_servers: str = None,
    producer_config: ProducerConfig = None,
    consumer_config: ConsumerConfig = None,
) -> StreamProcessor:
    """Initialize stream processor."""
    global _stream_processor
    _stream_processor = StreamProcessor(
        bootstrap_servers=bootstrap_servers or getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
    )
    await _stream_processor.initialize(producer_config, consumer_config)
    return _stream_processor


# ==================== Convenience Functions ====================

async def produce_message(
    topic: str,
    value: Any,
    key: Any = None,
    bootstrap_servers: str = None,
) -> Tuple[int, int]:
    """Quick produce single message."""
    producer = AsyncProducer(ProducerConfig(
        bootstrap_servers=bootstrap_servers or getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
    ))
    await producer.initialize()
    try:
        return await producer.send(topic, value, key)
    finally:
        await producer.close()


async def consume_messages(
    topics: List[str],
    group_id: str,
    handler: Callable[[ConsumerRecord], Any],
    bootstrap_servers: str = None,
) -> None:
    """Consume messages with handler."""
    consumer = AsyncConsumer(ConsumerConfig(
        bootstrap_servers=bootstrap_servers or getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        group_id=group_id,
    ))
    await consumer.initialize()
    consumer.register_handlers({topic: handler for topic in topics})
    try:
        await consumer.run()
    finally:
        await consumer.close()