"""Global Scale, Cloud Infrastructure & Enterprise Reliability models (Phase 16).

Cloud regions, deployment history, backup records, cluster status, health &
service metrics, autoscaling events, disaster recovery logs and chaos
(reliability) runs. These tables are platform-wide (not organization-scoped):
they describe the infrastructure the entire VCOS fleet runs on.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class CloudRegion(Base, TimestampMixin):
    """A deployed cloud region (aws/azure/gcp/onprem) with residency rules."""

    __tablename__ = "cloud_regions"
    __table_args__ = (
        Index("ix_cloud_regions_name", "name"),
        UniqueConstraint("name", name="uq_cloud_regions_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # aws|azure|gcp|onprem|multi
    provider: Mapped[str] = mapped_column(String(20), default="aws")
    location: Mapped[Optional[str]] = mapped_column(String(120))
    # asia|europe|north_america|south_america|africa|australia|middle_east
    continent: Mapped[str] = mapped_column(String(30), default="north_america")
    # active|degraded|offline|maintenance
    status: Mapped[str] = mapped_column(String(20), default="active")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    load_percent: Mapped[int] = mapped_column(Integer, default=0)
    # data residency compliance labels, e.g. ["gdpr", "soc2"]
    residency: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    endpoints: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    active_instances: Mapped[int] = mapped_column(Integer, default=0)
    degraded_instances: Mapped[int] = mapped_column(Integer, default=0)
    offline_instances: Mapped[int] = mapped_column(Integer, default=0)


class DeploymentRecord(Base, TimestampMixin):
    """Zero-downtime deployment history (rolling, blue-green, canary)."""

    __tablename__ = "deployment_history"
    __table_args__ = (
        Index("ix_deployment_history_status", "status"),
        Index("ix_deployment_history_service", "service"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(60))
    # blue_green|canary|rolling|rollback|validate
    strategy: Mapped[str] = mapped_column(String(20), default="rolling")
    # started|in_progress|promoted|completed|failed|rolled_back
    status: Mapped[str] = mapped_column(String(20), default="started")
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64))
    old_replicas: Mapped[int] = mapped_column(Integer, default=0)
    new_replicas: Mapped[int] = mapped_column(Integer, default=0)
    canary_percentage: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))


class BackupRecord(Base, TimestampMixin):
    """Backup lifecycle: hourly, daily, weekly, cross-region, verified, PITR."""

    __tablename__ = "backup_history"
    __table_args__ = (
        Index("ix_backup_history_kind_status", "kind", "status"),
        Index("ix_backup_history_region", "region"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # hourly|daily|weekly|cross_region|pitr
    # postgres|redis|neo4j|opensearch|object_storage|ai
    target: Mapped[str] = mapped_column(String(30), default="postgres")
    region: Mapped[Optional[str]] = mapped_column(String(60))
    # started|completed|failed|restoring|restored|expired
    status: Mapped[str] = mapped_column(String(20), default="started")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    checksum: Mapped[Optional[str]] = mapped_column(String(128))
    storage_key: Mapped[Optional[str]] = mapped_column(String(255))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))


class ClusterStatus(Base, TimestampMixin):
    """Replicated cluster health: primary/replica topology per region."""

    __tablename__ = "cluster_status"
    __table_args__ = (
        Index("ix_cluster_status_region_type", "region", "cluster_type"),
        Index("ix_cluster_status_status", "status"),
        UniqueConstraint("region", "cluster_type", "name", name="uq_cluster_status_region_type_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    region: Mapped[Optional[str]] = mapped_column(String(60))
    # postgres|redis|neo4j|opensearch|ai|gateway|object_storage|queue|search|graph
    cluster_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # primary|replica|standby|backup
    role: Mapped[str] = mapped_column(String(20), default="primary")
    # healthy|degraded|offline|recovering
    status: Mapped[str] = mapped_column(String(20), default="healthy")
    healthy_nodes: Mapped[int] = mapped_column(Integer, default=1)
    total_nodes: Mapped[int] = mapped_column(Integer, default=1)
    lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[Optional[str]] = mapped_column(String(30))
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class RegionStatus(Base, TimestampMixin):
    """Per-service region availability snapshots (load balancing targets)."""

    __tablename__ = "region_status"
    __table_args__ = (
        Index("ix_region_status_region_service", "region", "service"),
        Index("ix_region_status_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    region: Mapped[str] = mapped_column(String(60), nullable=False)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    # healthy|degraded|offline
    status: Mapped[str] = mapped_column(String(20), default="healthy")
    active_instances: Mapped[int] = mapped_column(Integer, default=0)
    degraded_instances: Mapped[int] = mapped_column(Integer, default=0)
    offline_instances: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    load_percent: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class HealthMetric(Base, TimestampMixin):
    """Infrastructure health time series (availability, latency, errors)."""

    __tablename__ = "health_metrics"
    __table_args__ = (
        Index("ix_health_metrics_region_service", "region", "service"),
        Index("ix_health_metrics_recorded", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    region: Mapped[Optional[str]] = mapped_column(String(60))
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    # availability|latency_ms|error_rate|cpu_percent|memory_percent|queue_depth|gpu_util_percent
    metric_name: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    # ok|warn|critical
    status: Mapped[str] = mapped_column(String(10), default="ok")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class ServiceMetric(Base, TimestampMixin):
    """Per-service operational metrics (requests, workers, queues, GPU)."""

    __tablename__ = "service_metrics"
    __table_args__ = (
        Index("ix_service_metrics_service_region", "service", "region"),
        Index("ix_service_metrics_recorded", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(60))
    metric_name: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class AutoscalingEvent(Base, TimestampMixin):
    """Horizontal autoscaling decisions (scale up / down) and outcomes."""

    __tablename__ = "autoscaling_events"
    __table_args__ = (
        Index("ix_autoscaling_events_region_resource", "region", "resource"),
        Index("ix_autoscaling_events_triggered", "triggered_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    region: Mapped[Optional[str]] = mapped_column(String(60))
    # api|workers|meeting|search|ai|db_replicas|cache|storage
    resource: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # scale_up|scale_down
    from_capacity: Mapped[int] = mapped_column(Integer, default=1)
    to_capacity: Mapped[int] = mapped_column(Integer, default=1)
    metric: Mapped[str] = mapped_column(String(40), default="cpu_percent")
    threshold: Mapped[float] = mapped_column(Float, default=70.0)
    observed: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    # triggered|applied|reverted|completed
    status: Mapped[str] = mapped_column(String(20), default="triggered")
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))


class DisasterRecoveryLog(Base, TimestampMixin):
    """Disaster recovery runs: failover, replica promotion, recovery testing."""

    __tablename__ = "disaster_recovery_logs"
    __table_args__ = (
        Index("ix_dr_logs_region_scenario", "region", "scenario"),
        Index("ix_dr_logs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    run_id: Mapped[Optional[str]] = mapped_column(String(32))
    region: Mapped[Optional[str]] = mapped_column(String(60))
    # region_outage|db_failover|worker_crash|storage_fallback|api_failover|recovery_test|replica_promotion
    scenario: Mapped[str] = mapped_column(String(40), nullable=False)
    # started|completed|failed|recovered
    status: Mapped[str] = mapped_column(String(20), default="started")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    steps: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    rpo_minutes: Mapped[int] = mapped_column(Integer, default=0)
    rto_minutes: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))


class ChaosRun(Base, TimestampMixin):
    """Reliability engineering chaos experiments (kill, fail, degrade)."""

    __tablename__ = "chaos_runs"
    __table_args__ = (
        Index("ix_chaos_runs_scenario", "scenario"),
        Index("ix_chaos_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    scenario: Mapped[str] = mapped_column(String(40), nullable=False)
    # kill_api_server|kill_replica|region_down|db_latency|worker_termination|network_partition
    target_region: Mapped[Optional[str]] = mapped_column(String(60))
    target_service: Mapped[Optional[str]] = mapped_column(String(60))
    # queued|running|completed|failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expected_impact: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    steps: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
