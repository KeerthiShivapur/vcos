-- VCOS table partitioning (Phase 16.5) - keeps platform tables bounded.
-- Partition the high-volume event and metric tables by time.

-- 1) Platform event stream: daily rollup + monthly partitions
CREATE TABLE IF NOT EXISTS events (
    id               VARCHAR(32)  NOT NULL,
    organization_id  VARCHAR(32),
    actor_id         VARCHAR(32),
    name             VARCHAR(120) NOT NULL,
    payload_json     TEXT,
    occurred_at      TIMESTAMPTZ  NOT NULL,
    processed_at     TIMESTAMPTZ,
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE IF NOT EXISTS events_2026_08 PARTITION OF events
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

-- 2) Service metrics: hot (7d) + warm (90d) partitions
CREATE TABLE IF NOT EXISTS service_metrics (
    id           VARCHAR(32) NOT NULL,
    service      VARCHAR(60) NOT NULL,
    region       VARCHAR(60),
    metric_name  VARCHAR(40) NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    unit         VARCHAR(20),
    recorded_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, recorded_at)
) PARTITION BY RANGE (recorded_at);

CREATE TABLE IF NOT EXISTS service_metrics_hot PARTITION OF service_metrics
    FOR VALUES FROM (MINVALUE) TO ('2026-08-14');
CREATE TABLE IF NOT EXISTS service_metrics_warm PARTITION OF service_metrics
    FOR VALUES FROM ('2026-08-14') TO ('2026-11-14');

-- 3) Autoscaling decisions get a rolling window too
CREATE TABLE IF NOT EXISTS autoscaling_events (
    id            VARCHAR(32) NOT NULL,
    region        VARCHAR(60),
    resource      VARCHAR(30) NOT NULL,
    direction     VARCHAR(10) NOT NULL,
    triggered_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, triggered_at)
) PARTITION BY RANGE (triggered_at);

-- Indexes on partitioned tables
CREATE INDEX IF NOT EXISTS ix_events_name_part ON events (name, occurred_at);
CREATE INDEX IF NOT EXISTS ix_metrics_service_part ON service_metrics (service, recorded_at);
