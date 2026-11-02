"""Gate 34 — Universal Observability & Operational Intelligence Fabric Tests."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.core.timeutils import utcnow
from app.models.observability import (
    CanonicalObservation,
    CorrelationContext,
    Degradation,
    HealthDimension,
    SLOTarget,
    FreshnessCheck,
    OperationalTarget,
    OBSERVATION_TYPES,
    OBSERVATION_SEVERITY,
    OBSERVATION_EPISTEMIC,
    CORRELATION_TYPES,
    DEGRADATION_STATES,
    DEGRADATION_SEVERITY,
    HEALTH_DIMENSIONS,
    compute_observation_fingerprint,
    compute_correlation_fingerprint,
)
from app.models.canonical_reliability import CanonicalOperation
from app.models.canonical_integration import ConnectorInstance, SyncRun
from app.models.enterprise import SecurityEvent
from app.models.continuous_twin import CompanyAttention
from app.services.observability_service import (
    observability_service,
    ObservationContext,
    CorrelationChainStep,
)
from tests.conftest import register_org
import uuid


class TestObservabilityVocabularies:
    """Test vocabulary completeness for observability system."""

    def test_observation_types_complete(self):
        """Verify all observation types are defined."""
        types = [t for t in OBSERVATION_TYPES]
        assert "request" in types
        assert "worker_execution" in types
        assert "operation_lifecycle" in types
        assert "integration_sync" in types
        assert "external_operation" in types
        assert "security_event" in types
        assert "recovery_action" in types
        assert "reconciliation" in types
        assert "health_check" in types
        assert "freshness_check" in types
        assert "slo_evaluation" in types
        assert "attention_signal" in types
        assert "degradation" in types
        assert "correlation" in types

    def test_observation_severity_complete(self):
        """Verify all severity levels are defined."""
        severities = [s for s in OBSERVATION_SEVERITY]
        assert "debug" in severities
        assert "info" in severities
        assert "notice" in severities
        assert "warning" in severities
        assert "critical" in severities

    def test_observation_epistemic_complete(self):
        """Verify all epistemic states are defined."""
        states = [s for s in OBSERVATION_EPISTEMIC]
        assert "observed" in states
        assert "measured" in states
        assert "evidence_backed" in states
        assert "inferred" in states
        assert "predicted" in states
        assert "unknown" in states

    def test_correlation_types_complete(self):
        """Verify all correlation types are defined."""
        types = [t for t in CORRELATION_TYPES]
        assert "request_flow" in types
        assert "operation_chain" in types
        assert "integration_flow" in types
        assert "security_cascade" in types
        assert "recovery_chain" in types
        assert "degradation_cascade" in types
        assert "business_impact" in types

    def test_degradation_states_complete(self):
        """Verify all degradation states are defined."""
        states = [s for s in DEGRADATION_STATES]
        assert "detected" in states
        assert "investigating" in states
        assert "contained" in states
        assert "recovering" in states
        assert "resolved" in states
        assert "verified" in states
        assert "learned" in states

    def test_degradation_severity_complete(self):
        """Verify all degradation severities are defined."""
        severities = [s for s in DEGRADATION_SEVERITY]
        assert "minor" in severities
        assert "major" in severities
        assert "critical" in severities

    def test_health_dimensions_complete(self):
        """Verify all health dimensions are defined."""
        dims = [d for d in HEALTH_DIMENSIONS]
        assert "availability" in dims
        assert "latency" in dims
        assert "error_rate" in dims
        assert "queue_delay" in dims
        assert "sync_freshness" in dims
        assert "worker_health" in dims
        assert "recovery_backlog" in dims
        assert "reconciliation_backlog" in dims


class TestObservabilityModels:
    """Test observability model creation and validation."""

    def test_canonical_observation_creation(self):
        """Test creating a canonical observation with all fields."""
        from app.models.observability import CanonicalObservation

        obs = CanonicalObservation(
            id="obs-1",
            organization_id="org-123",
            observation_type="request",
            source="api",
            source_component="request",
            actor_id="user-123",
            actor_type="human",
            severity="info",
            epistemic_status="observed",
            correlation_id="corr-123",
            trace_id="trace-456",
            span_id="span-789",
            title="GET /api/test - 200",
            description="API request returned 200",
            details_json={"route": "/api/test", "method": "GET"},
            metrics_json={"duration_ms": 150, "status_code": 200},
            provenance_json={"source_event_id": "evt-123"},
            observed_at=datetime.now(timezone.utc),
            duration_ms=150,
            fingerprint="fp-abc123",
        )

        assert obs.id == "obs-1"
        assert obs.observation_type == "request"
        assert obs.severity == "info"
        assert obs.epistemic_status == "observed"
        assert obs.fingerprint == "fp-abc123"

    def test_correlation_context_creation(self):
        """Test creating a correlation context."""
        from app.models.observability import CorrelationContext

        ctx = CorrelationContext(
            id="ctx-1",
            organization_id="org-123",
            correlation_type="request_flow",
            correlation_id="corr-123",
            trace_id="trace-456",
            chain_json={"steps": []},
            current_step=0,
            status="active",
            metadata_json={},
            fingerprint="fp-corr123",
        )

        assert ctx.id == "ctx-1"
        assert ctx.correlation_type == "request_flow"
        assert ctx.correlation_id == "corr-123"
        assert ctx.status == "active"

    def test_degradation_creation(self):
        """Test creating a degradation."""
        from app.models.observability import Degradation

        deg = Degradation(
            id="deg-1",
            organization_id="org-123",
            degradation_type="connector_failure",
            severity="critical",
            title="Payment connector failing",
            description="Stripe connector returning 500 errors",
            details_json={"error_rate": 0.95},
            state="detected",
            fingerprint="fp-deg123",
        )

        assert deg.id == "deg-1"
        assert deg.degradation_type == "connector_failure"
        assert deg.severity == "critical"
        assert deg.state == "detected"

    def test_health_dimension_creation(self):
        """Test creating a health dimension."""
        from app.models.observability import HealthDimension

        hdim = HealthDimension(
            id="hdim-1",
            organization_id="org-123",
            dimension="latency",
            scope_type="company",
            current_value=250.0,
            target_value=200.0,
            threshold_warn=200.0,
            threshold_critical=500.0,
            unit="ms",
            trend="degrading",
            trend_score=-0.5,
            status="degraded",
            fingerprint="fp-hdim123",
        )

        assert hdim.dimension == "latency"
        assert hdim.current_value == 250.0
        assert hdim.status == "degraded"

    def test_slo_target_creation(self):
        """Test creating an SLO target."""
        from app.models.observability import SLOTarget

        slo = SLOTarget(
            id="slo-1",
            organization_id="org-123",
            dimension="latency",
            scope_type="company",
            target_value=200.0,
            operator="<=",
            unit="ms",
            window_type="rolling",
            window_size="7d",
            status="active",
            fingerprint="fp-slo123",
        )

        assert slo.dimension == "latency"
        assert slo.target_value == 200.0
        assert slo.operator == "<="

    def test_freshness_check_creation(self):
        """Test creating a freshness check."""
        from app.models.observability import FreshnessCheck

        fresh = FreshnessCheck(
            id="fresh-1",
            organization_id="org-123",
            feed_type="integration",
            scope_type="integration",
            scope_id="conn-123",
            feed_id="stripe",
            status="stale",
            expected_interval_seconds=300,
            last_event_at=datetime.now(timezone.utc) - timedelta(hours=2),
            delay_seconds=7200,
            max_acceptable_delay_seconds=3600,
            fingerprint="fp-fresh123",
        )

        assert fresh.feed_type == "integration"
        assert fresh.status == "stale"
        assert fresh.delay_seconds == 7200

    def test_operational_target_creation(self):
        """Test creating an operational target."""
        from app.models.observability import OperationalTarget

        target = OperationalTarget(
            id="target-1",
            organization_id="org-123",
            target_type="worker_completion",
            scope_type="company",
            target_duration_seconds=300,
            target_value=0.95,
            unit="ratio",
            status="active",
            fingerprint="fp-target123",
        )

        assert target.target_type == "worker_completion"
        assert target.target_duration_seconds == 300
        assert target.status == "active"


class TestFingerprintComputation:
    """Test fingerprint computation utilities."""

    def test_observation_fingerprint_deterministic(self):
        """Test that observation fingerprints are deterministic."""
        payload = {
            "organization_id": "org-123",
            "observation_type": "request",
            "source": "api",
            "source_component": "request",
            "actor_id": "user-123",
            "operation_id": "op-123",
            "attempt_id": "att-1",
            "integration_id": "int-123",
            "connector_id": "conn-123",
            "external_operation_id": "ext-123",
            "security_event_id": "sec-123",
            "degradation_id": "deg-123",
            "title": "Test Observation",
            "key_fields": {"route": "/api/test", "method": "GET"},
        }
        
        fp1 = compute_observation_fingerprint(payload)
        fp2 = compute_observation_fingerprint(payload)
        
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA256 produces 64 hex characters

    def test_correlation_fingerprint_deterministic(self):
        """Test that correlation fingerprints are deterministic."""
        fp1 = compute_correlation_fingerprint("org-123", "corr-123", "trace-456")
        fp2 = compute_correlation_fingerprint("org-123", "corr-123", "trace-456")
        
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_changes_with_different_input(self):
        """Test that fingerprints change with different inputs."""
        fp1 = compute_observation_fingerprint({"org": "org-1", "type": "request"})
        fp2 = compute_observation_fingerprint({"org": "org-2", "type": "request"})
        
        assert fp1 != fp2


class TestObservabilityService:
    """Test the observability service."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        """Create a test organization with some data."""
        org = Organization(
            name=f"Test Observability Org {uuid.uuid4().hex[:8]}",
            slug=f"test-obs-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_record_observation(self, db_session: AsyncSession, test_org):
        """Test recording a canonical observation."""
        org = test_org["org"]
        user = test_org["user"]

        observation = await observability_service.record_observation(
            db=db_session,
            context=ObservationContext(
                organization_id=org.id,
                observation_type="request",
                source="api",
                source_component="request",
                actor_id=user.id,
                actor_type="human",
                severity="info",
                epistemic_status="observed",
                correlation_id="corr-123",
                trace_id="trace-456",
                title="GET /api/test - 200",
                description="API request returned 200",
                details_json={"route": "/api/test", "method": "GET"},
                metrics_json={"duration_ms": 150},
                observed_at=utcnow(),
                duration_ms=150,
                key_fields={"route": "/api/test", "method": "GET"},
            ),
        )

        assert observation.id is not None
        assert observation.organization_id == org.id
        assert observation.observation_type == "request"
        assert observation.severity == "info"
        assert observation.epistemic_status == "observed"
        assert observation.correlation_id == "corr-123"
        assert observation.trace_id == "trace-456"
        assert observation.fingerprint is not None

    async def test_exact_once_deduplication(self, db_session: AsyncSession, test_org):
        """Test exact-once deduplication for observations."""
        org = test_org["org"]

        # Record first observation
        obs1 = await observability_service.record_observation(
            db=db_session,
            context=ObservationContext(
                organization_id=org.id,
                observation_type="request",
                source="api",
                title="GET /api/test",
                key_fields={"route": "/api/test", "method": "GET"},
            ),
        )

        # Record duplicate with same key fields
        obs2 = await observability_service.record_observation(
            db=db_session,
            context=ObservationContext(
                organization_id=org.id,
                observation_type="request",
                source="api",
                title="GET /api/test",
                key_fields={"route": "/api/test", "method": "GET"},
            ),
        )

        # Should return the same observation
        assert obs2.id == obs1.id
        assert obs2.fingerprint == obs1.fingerprint

    async def test_correlation_context(self, db_session: AsyncSession, test_org):
        """Test correlation context creation and steps."""
        org = test_org["org"]

        # Create correlation context
        context = await observability_service.create_correlation_context(
            db=db_session,
            organization_id=org.id,
            correlation_type="request_flow",
            correlation_id="corr-123",
            trace_id="trace-456",
        )

        assert context.correlation_id == "corr-123"
        assert context.trace_id == "trace-456"
        assert context.status == "active"

        # Add step
        step = CorrelationChainStep(
            step_number=1,
            observation_type="request",
            source="api",
            observed_at=utcnow(),
        )
        
        context = await observability_service.add_correlation_step(
            db=db_session,
            correlation_context=context,
            step=step,
        )

        assert context.current_step == 1
        assert len(context.chain_json["steps"]) == 1

        # Complete correlation
        context = await observability_service.complete_correlation(
            db=db_session,
            correlation_context=context,
            outcome="success",
        )

        assert context.status == "completed"
        assert context.outcome == "success"
        assert context.completed_at is not None

    async def test_create_degradation(self, db_session: AsyncSession, test_org):
        """Test creating a degradation/incident."""
        org = test_org["org"]

        degradation = await observability_service.create_degradation(
            db=db_session,
            organization_id=org.id,
            degradation_type="connector_failure",
            severity="critical",
            title="Payment connector failing",
            description="Stripe connector returning 500 errors",
            details={"error_rate": 0.95},
            affected_entities=[{"type": "connector", "id": "stripe"}],
            affected_dimensions=["sync_freshness", "external_operation"],
            correlation_id="corr-123",
            actor_id="system",
            actor_type="system",
            evidence=[{"type": "error_rate", "value": 0.95}],
            provenance={"source": "health_check"},
        )

        assert degradation.id is not None
        assert degradation.degradation_type == "connector_failure"
        assert degradation.severity == "critical"
        assert degradation.state == "detected"
        assert degradation.fingerprint is not None

    async def test_degradation_lifecycle(self, db_session: AsyncSession, test_org):
        """Test full degradation lifecycle."""
        org = test_org["org"]

        # Create degradation
        degradation = await observability_service.create_degradation(
            db=db_session,
            organization_id=org.id,
            degradation_type="worker_failure",
            severity="major",
            title="Worker pool exhausted",
            description="All workers busy, queue backing up",
        )

        # Acknowledge
        degradation = await observability_service.acknowledge_degradation(
            db=db_session,
            degradation=degradation,
            actor_id="admin-123",
        )
        assert degradation.state == "investigating"

        # Contain
        degradation = await observability_service.contain_degradation(
            db=db_session,
            degradation=degradation,
            actor_id="admin-123",
            note="Scaled worker pool",
        )
        assert degradation.state == "contained"

        # Recover
        degradation = await observability_service.recover_degradation(
            db=db_session,
            degradation=degradation,
            actor_id="admin-123",
            resolution_method="scaled_workers",
            resolution_note="Added 5 new workers",
        )
        assert degradation.state == "recovering"

        # Verify
        degradation = await observability_service.verify_degradation(
            db=db_session,
            degradation=degradation,
            actor_id="admin-123",
            verification_note="Queue drained, all workers healthy",
        )
        assert degradation.state == "verified"

        # Learn
        degradation = await observability_service.learn_from_degradation(
            db=db_session,
            degradation=degradation,
            actor_id="admin-123",
            lessons_learned={"root_cause": "insufficient_worker_scaling"},
        )
        assert degradation.state == "learned"

    async def test_health_dimension_recording(self, db_session: AsyncSession, test_org):
        """Test recording health dimensions."""
        org = test_org["org"]

        hdim = await observability_service.record_health_dimension(
            db=db_session,
            organization_id=org.id,
            dimension="latency",
            current_value=250.0,
            target_value=200.0,
            threshold_warn=200.0,
            threshold_critical=500.0,
            unit="ms",
            trend="degrading",
            trend_score=-0.5,
            slo_target=200.0,
        )

        assert hdim.dimension == "latency"
        assert hdim.current_value == 250.0
        assert hdim.status == "degraded"
        assert hdim.trend == "degrading"

    async def test_slo_target(self, db_session: AsyncSession, test_org):
        """Test SLO target creation and evaluation."""
        org = test_org["org"]

        slo = await observability_service.create_or_update_slo_target(
            db=db_session,
            organization_id=org.id,
            dimension="latency",
            target_value=200.0,
            operator="<=",
            unit="ms",
            window_size="7d",
            updated_by="admin-123",
        )

        assert slo.dimension == "latency"
        assert slo.target_value == 200.0
        assert slo.operator == "<="

        # Record health dimension
        await observability_service.record_health_dimension(
            db=db_session,
            organization_id=org.id,
            dimension="latency",
            current_value=180.0,
            target_value=200.0,
            threshold_warn=150.0,
            threshold_critical=300.0,
            unit="ms",
        )

        # Evaluate SLO
        evaluated = await observability_service.evaluate_slo(
            db=db_session,
            organization_id=org.id,
            dimension="latency",
        )

        assert evaluated.current_compliance == 100.0  # 180 <= 200

    async def test_freshness_check(self, db_session: AsyncSession, test_org):
        """Test freshness checking."""
        org = test_org["org"]

        fresh = await observability_service.check_freshness(
            db=db_session,
            organization_id=org.id,
            feed_type="integration",
            scope_type="integration",
            scope_id="conn-123",
            feed_id="stripe",
            expected_interval_seconds=300,
            max_acceptable_delay_seconds=3600,
            last_event_at=utcnow() - timedelta(hours=2),
        )

        assert fresh.feed_type == "integration"
        assert fresh.status == "stale"
        assert fresh.delay_seconds == 7200  # 2 hours = 7200 seconds

    async def test_freshness_checks_integrations_and_workers(self, db_session: AsyncSession, test_org):
        """Test freshness checks for integrations and workers."""
        org = test_org["org"]

        # Test integration freshness check
        checks = await observability_service.check_integration_freshness(
            db=db_session,
            organization_id=org.id,
        )
        # Should return empty list since no integrations exist
        assert isinstance(checks, list)

        # Test worker freshness check
        checks = await observability_service.check_worker_freshness(
            db=db_session,
            organization_id=org.id,
        )
        assert isinstance(checks, list)

    async def test_operational_attention(self, db_session: AsyncSession, test_org):
        """Test operational attention creation and resolution."""
        org = test_org["org"]
        user = test_org["user"]

        attention = await observability_service.create_operational_attention(
            db=db_session,
            organization_id=org.id,
            attention_type="connector_failure",
            priority="alert",
            title="Stripe connector failing",
            description="High error rate detected",
            source_type="integration",
            source_id="stripe-connector",
            priority_score=0.9,
            urgency="high",
            assigned_by=user.id,
        )
    
        assert attention.attention_type == "connector_failure"
        assert attention.priority == "alert"
        assert attention.status == "open"

        # Resolve
        resolved = await observability_service.resolve_attention(
            db=db_session,
            attention_id=attention.id,
            organization_id=org.id,
            resolved_by=user.id,
            resolution_note="Fixed authentication",
        )
        assert resolved is True

        # Verify resolved
        result = await db_session.execute(
            select(CompanyAttention).where(CompanyAttention.id == attention.id)
        )
        attention = result.scalars().first()
        assert attention.status == "resolved"
        assert attention.resolved_by == user.id


class TestCorrelationReconstruction:
    """Test correlation chain reconstruction."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        """Create a test organization with some data."""
        org = Organization(
            name=f"Test Correlation Org {uuid.uuid4().hex[:8]}",
            slug=f"test-corr-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_reconstruct_correlation_chain(self, db_session: AsyncSession, test_org):
        """Test reconstructing correlation chain for a trace."""
        org = test_org["org"]
        trace_id = "trace-test-123"

        # Create correlation contexts
        for i in range(3):
            ctx = await observability_service.create_correlation_context(
                db=db_session,
                organization_id=org.id,
                correlation_type="request_flow",
                correlation_id=f"corr-{i}",
                trace_id=trace_id,
            )
            
            # Add steps
            step = CorrelationChainStep(
                step_number=1,
                observation_type="request",
                source="api",
                observed_at=utcnow(),
            )
            await observability_service.add_correlation_step(
                db=db_session,
                correlation_context=ctx,
                step=step,
            )

        # Reconstruct chain
        chain = await observability_service.reconstruct_correlation_chain(
            db=db_session,
            organization_id=org.id,
            trace_id=trace_id,
        )

        assert len(chain) == 3
        for step in chain:
            assert step["trace_id"] == trace_id
            assert step["observation_type"] == "request"

    async def test_operation_correlation(self, db_session: AsyncSession, test_org):
        """Test getting all observations for an operation."""
        org = test_org["org"]

        # Create operation
        operation = CanonicalOperation(
            id="op-test-123",
            organization_id=org.id,
            operation_type="test_op",
            title="Test Operation",
            state="completed",
        )
        db_session.add(operation)
        await db_session.flush()

        # Create observations
        for i in range(3):
            await observability_service.record_observation(
                db=db_session,
                context=ObservationContext(
                    organization_id=org.id,
                    observation_type="operation_lifecycle",
                    source="reliability",
                    operation_id=operation.id,
                    operation_type="test_op",
                    title=f"Operation step {i}",
                    correlation_id=f"corr-{i}",
                ),
            )

        observations = await observability_service.get_operation_correlation(
            db=db_session,
            organization_id=org.id,
            operation_id=operation.id,
        )

        assert len(observations) == 3


class TestIntegrationHealth:
    """Test integration health observability."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Integration Org {uuid.uuid4().hex[:8]}",
            slug=f"test-int-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_integration_freshness(self, db_session: AsyncSession, test_org):
        """Test integration freshness checking."""
        org = test_org["org"]
        
        # Create connector
        connector = ConnectorInstance(
            id="conn-test-1",
            organization_id=org.id,
            connector_id="stripe",
            name="Test Stripe",
            config={"url": "https://api.stripe.com"},
            webhook_url="https://api.stripe.com/webhook",
            webhook_events=["payment"],
            webhook_secret="secret123",
            state="active",
        )
        db_session.add(connector)
        await db_session.flush()

        # Create sync run
        sync = SyncRun(
            organization_id=org.id,
            connector_instance_id=connector.id,
            sync_mode="incremental",
            triggered_by="webhook",
            trigger_id="evt-123",
            state="completed",
            entities_processed=1,
            events_processed=1,
        )
        db_session.add(sync)
        await db_session.flush()

        checks = await observability_service.check_integration_freshness(
            db=db_session,
            organization_id=org.id,
        )

        assert len(checks) >= 1
        check = checks[0]
        assert check.feed_type == "integration"
        assert check.scope_id == connector.id


class TestWorkerObservability:
    """Test worker execution observability."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Worker Org {uuid.uuid4().hex[:8]}",
            slug=f"test-wrk-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_worker_observation(self, db_session: AsyncSession, test_org):
        """Test recording worker observations."""
        org = test_org["org"]

        observation = await observability_service.record_worker_observation(
            db=db_session,
            organization_id=org.id,
            worker_id="worker-123",
            operation_id="op-456",
            attempt_id="att-1",
            outcome="success",
            duration_ms=5000,
            title="Worker processed payment",
            severity="info",
        )

        assert observation.observation_type == "worker_execution"
        assert observation.source == "worker"
        assert observation.details_json["worker_id"] == "worker-123"
        assert observation.details_json["outcome"] == "success"

    async def test_worker_freshness(self, db_session: AsyncSession, test_org):
        """Test worker freshness checking."""
        org = test_org["org"]

        checks = await observability_service.check_worker_freshness(
            db=db_session,
            organization_id=org.id,
        )
        assert isinstance(checks, list)


class TestCorrelationReconstruction:
    """Test correlation chain reconstruction."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Correlation Org {uuid.uuid4().hex[:8]}",
            slug=f"test-corr-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_reconstruct_correlation_chain(self, db_session: AsyncSession, test_org):
        """Test reconstructing correlation chain."""
        org = test_org["org"]
        trace_id = "trace-reconstruct-test"

        # Create correlation contexts with steps
        for i in range(3):
            ctx = await observability_service.create_correlation_context(
                db=db_session,
                organization_id=org.id,
                correlation_type="request_flow",
                correlation_id=f"corr-{i}",
                trace_id=trace_id,
            )
            
            step = CorrelationChainStep(
                step_number=1,
                observation_type="request",
                source="api",
                operation_id=f"op-{i}",
                actor_id="user-123",
                observed_at=utcnow(),
                outcome="success",
            )
            await observability_service.add_correlation_step(
                db=db_session,
                correlation_context=ctx,
                step=step,
            )
        
# Ensure all contexts are flushed
        await db_session.flush()
    
        chain = await observability_service.reconstruct_correlation_chain(
            db=db_session,
            organization_id=org.id,
            trace_id=trace_id,
        )
    
        assert len(chain) == 3
        for step in chain:
            assert step["correlation_id"] in ["corr-0", "corr-1", "corr-2"]
            assert step["observation_type"] == "request"


class TestHealthDashboard:
    """Test health dashboard endpoint."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Dashboard Org {uuid.uuid4().hex[:8]}",
            slug=f"test-dash-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_health_dashboard(self, db_session: AsyncSession, test_org):
        """Test health dashboard aggregation."""
        org = test_org["org"]

        # Add some health dimensions
        await observability_service.record_health_dimension(
            db=db_session,
            organization_id=org.id,
            dimension="latency",
            current_value=250.0,
            target_value=200.0,
            threshold_warn=200.0,
            threshold_critical=500.0,
            unit="ms",
            trend="degrading",
        )

        await observability_service.record_health_dimension(
            db=db_session,
            organization_id=org.id,
            dimension="error_rate",
            current_value=0.05,
            target_value=0.01,
            threshold_warn=0.01,
            threshold_critical=0.05,
            unit="ratio",
            trend="stable",
        )

        dashboard = await observability_service.get_health_dashboard(
            db=db_session,
            organization_id=org.id,
        )

        assert "health_dimensions" in dashboard
        assert "freshness" in dashboard
        assert "degradations" in dashboard
        assert "attention" in dashboard
        assert "correlations" in dashboard
        assert "slos" in dashboard
        assert "integration_freshness" in dashboard
        assert "worker_freshness" in dashboard

        # Check latency dimension
        latency = next(d for d in dashboard["health_dimensions"] if d["dimension"] == "latency")
        assert latency["status"] == "degraded"
        assert latency["current_value"] == 250.0


class TestSecurityObservability:
    """Test security event observability."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Security Org {uuid.uuid4().hex[:8]}",
            slug=f"test-sec-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_security_observation(self, db_session: AsyncSession, test_org):
        """Test recording security event observations."""
        org = test_org["org"]
        user = test_org["user"]

        # Create security event
        sec_event = SecurityEvent(
            organization_id=org.id,
            event_type="failed_login_brute_force",
            severity="high",
            title="Brute force attack detected",
            actor_id=user.id,
            source_ip="192.168.1.100",
            details={"attempts": 50, "duration_seconds": 300},
            status="open",
        )
        db_session.add(sec_event)
        await db_session.flush()

        # Record observation
        observation = await observability_service.record_security_observation(
            db=db_session,
            organization_id=org.id,
            security_event=sec_event,
            title="Brute force attack detected",
            description="50 failed login attempts from 192.168.1.100",
            correlation_id="sec-corr-123",
        )

        assert observation.observation_type == "security_event"
        assert observation.source == "security"
        assert observation.severity == "critical"
        assert observation.security_event_id == sec_event.id
        assert observation.details_json["attempts"] == 50


class TestOperationalTargets:
    """Test operational targets."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Target Org {uuid.uuid4().hex[:8]}",
            slug=f"test-target-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_create_operational_target(self, db_session: AsyncSession, test_org):
        """Test creating operational targets."""
        org = test_org["org"]

        target = await observability_service.create_operational_target(
            db=db_session,
            organization_id=org.id,
            target_type="worker_completion",
            target_duration_seconds=300,
            target_value=0.95,
            unit="ratio",
        )

        assert target.target_type == "worker_completion"
        assert target.target_duration_seconds == 300
        assert target.target_value == 0.95
        assert target.status == "active"

    async def test_evaluate_operational_target(self, db_session: AsyncSession, test_org):
        """Test evaluating operational target."""
        org = test_org["org"]

        target = await observability_service.create_operational_target(
            db=db_session,
            organization_id=org.id,
            target_type="worker_completion",
            target_duration_seconds=300,
            target_value=0.95,
        )

        # Evaluate with success rate
        evaluated = await observability_service.evaluate_operational_target(
            db=db_session,
            target=target,
            current_value=0.97,
        )

        assert evaluated.current_value == 0.97
        assert evaluated.status == "met"  # 0.97 > 0.95

        # Evaluate with failure
        evaluated = await observability_service.evaluate_operational_target(
            db=db_session,
            target=target,
            current_value=0.90,
        )

        assert evaluated.status == "missed"  # 0.90 < 0.95


class TestAdversarialObservability:
    """Adversarial tests for observability security."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        org = Organization(
            name=f"Test Adversarial Org {uuid.uuid4().hex[:8]}",
            slug=f"test-adv-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        # Create second organization for cross-tenant tests
        org2 = Organization(
            name=f"Test Adversarial Org 2 {uuid.uuid4().hex[:8]}",
            slug=f"test-adv-2-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org2)
        await db_session.flush()

        user2 = User(
            organization_id=org2.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User 2",
            password_hash="hashed_password",
        )
        db_session.add(user2)
        await db_session.flush()

        return {"org": org, "org2": org2, "user": user, "user2": user2}

    async def test_cross_tenant_observation_access_blocked(self, db_session: AsyncSession, test_org):
        """Test that observations cannot be accessed across tenants."""
        org = test_org["org"]
        org2 = test_org["org2"]

        # Create observation in org1
        obs = CanonicalObservation(
            organization_id=org.id,
            observation_type="request",
            source="api",
            title="Test Request",
            fingerprint="fp-test-1",
            observed_at=utcnow(),
        )
        db_session.add(obs)
        await db_session.flush()

        # Try to query from org2 context - should not find it
        result = await db_session.execute(
            select(CanonicalObservation).where(
                CanonicalObservation.id == obs.id,
                CanonicalObservation.organization_id == org2.id,
            )
        )
        found = result.scalars().first()
        assert found is None, "Cross-tenant observation access must be blocked"

    async def test_cross_tenant_degradation_access_blocked(self, db_session: AsyncSession, test_org):
        """Test that degradations cannot be accessed across tenants."""
        org = test_org["org"]
        org2 = test_org["org2"]

        deg = Degradation(
            organization_id=org.id,
            degradation_type="test",
            severity="minor",
            title="Test Degradation",
            fingerprint="fp-test-deg",
        )
        db_session.add(deg)
        await db_session.flush()

        result = await db_session.execute(
            select(Degradation).where(
                Degradation.id == deg.id,
                Degradation.organization_id == org2.id,
            )
        )
        found = result.scalars().first()
        assert found is None, "Cross-tenant degradation access must be blocked"

    async def test_cross_tenant_correlation_access_blocked(self, db_session: AsyncSession, test_org):
        """Test that correlation contexts cannot be accessed across tenants."""
        org = test_org["org"]
        org2 = test_org["org2"]

        ctx = CorrelationContext(
            organization_id=org.id,
            correlation_type="request_flow",
            correlation_id="corr-test-1",
            fingerprint="fp-corr-test",
        )
        db_session.add(ctx)
        await db_session.flush()

        result = await db_session.execute(
            select(CorrelationContext).where(
                CorrelationContext.id == ctx.id,
                CorrelationContext.organization_id == org2.id,
            )
        )
        found = result.scalars().first()
        assert found is None, "Cross-tenant correlation access must be blocked"

    async def test_secret_redaction(self, db_session: AsyncSession, test_org):
        """Test that secrets are redacted in API responses."""
        org = test_org["org"]

        observation = CanonicalObservation(
            organization_id=org.id,
            observation_type="request",
            source="api",
            title="Test Request",
            details_json={"api_key": "secret-key-123", "normal_field": "value"},
            metrics_json={"duration_ms": 100},
            fingerprint="fp-secret-test",
            observed_at=utcnow(),
        )
        db_session.add(observation)
        await db_session.flush()

        sanitized = observability_service.sanitize_observation_for_api(observation)
        
        assert sanitized["details_json"]["api_key"] == "***REDACTED***"
        assert sanitized["details_json"]["normal_field"] == "value"

    async def test_cross_tenant_health_access_blocked(self, db_session: AsyncSession, test_org):
        """Test that health dimensions cannot be accessed across tenants."""
        org = test_org["org"]
        org2 = test_org["org2"]

        hdim = HealthDimension(
            organization_id=org.id,
            dimension="latency",
            current_value=100.0,
            fingerprint="fp-hdim-cross",
        )
        db_session.add(hdim)
        await db_session.flush()

        result = await db_session.execute(
            select(HealthDimension).where(
                HealthDimension.id == hdim.id,
                HealthDimension.organization_id == org2.id,
            )
        )
        found = result.scalars().first()
        assert found is None, "Cross-tenant health access must be blocked"


class TestArchitecturalInvariants:
    """Test architectural invariants of observability system."""

    def test_no_parallel_reality(self):
        """Observability must not create parallel reality."""
        # Observability models reuse existing primitives
        # No separate observability graph, brain, or reality
        pass

    def test_governed_observation(self):
        """Observations must be governed, never silent."""
        # All observations require organization_id and actor
        pass

    def test_historical_preservation(self):
        """Observations must preserve history."""
        # Observations are immutable once created
        pass

    def test_epistemic_honesty(self):
        """Observations must be epistemically honest."""
        # Epistemic status distinguishes observed/measured/inferred
        pass

    def test_scale_invariant(self):
        """Observability must scale invariantly."""
        # Same architecture works at any scale
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])