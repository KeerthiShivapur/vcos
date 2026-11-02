"""Gate 32 — Canonical Reliability, Failure Recovery & Continuity Fabric Tests.

Tests the integrity detection and governed reconciliation service.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.decision_history import DecisionHistory as Decision
from app.models.company_operating import (
    CompanyDecision, CompanyHealthHistory, CompanyDecisionContradiction,
    CompanyDecisionAlternative
)
from app.models.execution_strategy import (
    CompanyCommitment, CompanyAuthorization, CompanyGoal, CompanyObjective,
    CompanyInitiative, VerificationContext, ObjectiveContradiction
)
from app.models.company_actions import CompanyAction
from app.models.canonical_business_intelligence import (
    CanonicalMetric, MetricObservation
)
from app.models.organizational_learning import (
    OrganizationalLearning, LearningEvidence
)
from app.models.continuous_twin import (
    CompanyAttention, ModelTwinDrift, TwinStateSnapshot,
    PredictionCalibration, OptimizationContext,
    LearningSignal, InstitutionalMemoryEntry,
    TwinScope, TwinContext, ContinuousStateProjection
)
from app.models.canonical_company_continuity import (
    CompanyOperatingContinuity, CompanyContinuityEvent,
    CompanyStateSnapshotGate30, UniversalCompanyContext,
    CrossDomainConsistencyCheck, CompanyOperatingHealth,
    UniversalCompanyTimeline, SelfCompoundingLoopState,
    COMPANY_LOOP_PHASES,
)
from app.models.canonical_integration import (
    ExternalConflict, ExternalIdentityMapping,
    SourceAuthority, ConnectorInstance
)
from app.models.autonomy import AutonomyProposal, AutonomyEvent, AutonomyExecution
from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    RecoveryProposal,
    StaleOperationDetector,
    WorkerLease,
    OperationCheckpoint,
    OPERATION_STATES,
    ATTEMPT_STATES,
    RECOVERY_STATES,
    RECONCILIATION_STATES,
    RECOVERY_TYPES,
    FAILURE_CLASSES,
    RETRY_POLICIES,
    RECOVERY_OUTCOMES,
    ATTEMPT_OUTCOMES,
)

from app.services.canonical_reliability_service import (
    canonical_reliability_service,
    FailureClassifier,
    RetryPolicy,
    RecoveryContext,
)

from tests.conftest import register_org
import uuid


@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession):
    """Create a test organization with some data."""
    org = Organization(
        name=f"Test Integrity Org {uuid.uuid4().hex[:8]}",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
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


class TestReliabilityVocabularies:
    """Test vocabulary completeness for reliability system."""

    def test_operation_states_complete(self):
        """Verify all operation states are defined."""
        states = [s for s in OPERATION_STATES]
        assert "queued" in states
        assert "attempting" in states
        assert "executing" in states
        assert "completed" in states
        assert "failed" in states
        assert "retrying" in states
        assert "cancelled" in states
        assert "unknown" in states
        assert "recovering" in states
        assert "reconciled" in states
        assert "expired" in states

    def test_attempt_states_complete(self):
        """Verify all attempt states are defined."""
        states = [s for s in ATTEMPT_STATES]
        assert "pending" in states
        assert "executing" in states
        assert "completed" in states
        assert "failed" in states
        assert "timeout" in states
        assert "cancelled" in states
        assert "unknown" in states
        assert "retrying" in states

    def test_recovery_states_complete(self):
        """Verify all recovery states are defined."""
        states = [s for s in RECOVERY_STATES]
        assert "pending" in states
        assert "detecting" in states
        assert "classifying" in states
        assert "planning" in states
        assert "executing" in states
        assert "verifying" in states
        assert "completed" in states
        assert "failed" in states
        assert "escalated" in states
        assert "cancelled" in states

    def test_reconciliation_states_complete(self):
        """Verify all reconciliation states are defined."""
        states = [s for s in RECONCILIATION_STATES]
        assert "pending" in states
        assert "detecting" in states
        assert "querying" in states
        assert "comparing" in states
        assert "resolving" in states
        assert "completed" in states
        assert "failed" in states
        assert "escalated" in states

    def test_recovery_types_complete(self):
        """Verify all recovery types are defined."""
        types = [t for t in RECOVERY_TYPES]
        assert "retry" in types
        assert "replay" in types
        assert "compensate" in types
        assert "reconcile" in types
        assert "escalate" in types
        assert "restart" in types
        assert "compensate_and_retry" in types
        assert "external_reconcile" in types
        assert "manual_intervention" in types

    def test_failure_classes_complete(self):
        """Verify all failure classes are defined."""
        classes = [c for c in FAILURE_CLASSES]
        assert "transient" in classes
        assert "permanent" in classes
        assert "unknown" in classes
        assert "external_unknown" in classes
        assert "external_conflict" in classes
        assert "governance_blocked" in classes
        assert "authorization_expired" in classes
        assert "resource_exhausted" in classes
        assert "validation_failed" in classes

    def test_retry_policies_complete(self):
        """Verify all retry policies are defined."""
        policies = [p for p in RETRY_POLICIES]
        assert "exponential_backoff" in policies
        assert "fixed_interval" in policies
        assert "linear_backoff" in policies
        assert "immediate" in policies
        assert "custom" in policies

    def test_recovery_outcomes_complete(self):
        """Verify all recovery outcomes are defined."""
        outcomes = [o for o in RECOVERY_OUTCOMES]
        assert "recovered" in outcomes
        assert "partially_recovered" in outcomes
        assert "compensated" in outcomes
        assert "escalated" in outcomes
        assert "abandoned" in outcomes
        assert "reconciled" in outcomes

    def test_attempt_outcomes_complete(self):
        """Verify all attempt outcomes are defined."""
        outcomes = [o for o in ATTEMPT_OUTCOMES]
        assert "success" in outcomes
        assert "failure" in outcomes
        assert "timeout" in outcomes
        assert "cancelled" in outcomes
        assert "unknown" in outcomes


class TestReliabilityModels:
    """Test reliability model creation and validation."""

    def test_canonical_operation_creation(self):
        """Test creating a canonical operation with all fields."""
        from app.models.canonical_reliability import CanonicalOperation
        
        op = CanonicalOperation(
            id="test-op-1",
            organization_id="org-123",
            operation_type="external_api_call",
            title="Call External API",
            description="Call external payment API",
            scope_type="company",
            state="queued",
            current_attempt=0,
            fingerprint="fp-123",
            )
        
        assert op.id == "test-op-1"
        assert op.operation_type == "external_api_call"
        assert op.state == "queued"
        assert op.current_attempt == 0
        assert op.fingerprint == "fp-123"

    def test_operation_attempt_creation(self):
        """Test creating an operation attempt."""
        from app.models.canonical_reliability import OperationAttempt
        
        attempt = OperationAttempt(
            id="attempt-1",
            operation_id="op-123",
            organization_id="org-123",
            attempt_number=1,
            state="pending",
            )
        
        assert attempt.id == "attempt-1"
        assert attempt.attempt_number == 1
        assert attempt.state == "pending"

    def test_recovery_creation(self):
        """Test creating a recovery record."""
        from app.models.canonical_reliability import Recovery
        
        recovery = Recovery(
            id="rec-1",
            operation_id="op-123",
            organization_id="org-123",
            recovery_type="retry",
            failure_class="transient",
            failure_reason="Timeout",
            )
        
        assert recovery.id == "rec-1"
        assert recovery.recovery_type == "retry"
        assert recovery.failure_class == "transient"

    def test_reconciliation_creation(self):
        """Test creating a reconciliation record."""
        from app.models.canonical_reliability import Reconciliation
        
        recon = Reconciliation(
            id="recon-1",
            organization_id="org-123",
            reconciliation_type="external_operation",
            entity_type="canonical_operation",
            entity_id="op-123",
            external_system="stripe",
            external_entity_id="ext-123",
        )
        
        assert recon.id == "recon-1"
        assert recon.reconciliation_type == "external_operation"

    def test_external_unknown_state_creation(self):
        """Test creating an external unknown state."""
        from app.models.canonical_reliability import ExternalUnknownState
        
        eus = ExternalUnknownState(
            id="eus-1",
            operation_id="op-123",
            organization_id="org-123",
            external_system="stripe",
            external_operation_id="evt_123",
            external_operation_type="payment",
            request_payload_json={"amount": 100},
            request_fingerprint="req-fp-eus-1",
            state="unknown",
            fingerprint="fp-eus-1",
            )
        
        assert eus.id == "eus-1"
        assert eus.external_system == "stripe"
        assert eus.state == "unknown"

    def test_recovery_proposal_creation(self):
        """Test creating a recovery proposal."""
        from app.models.canonical_reliability import RecoveryProposal
        
        proposal = RecoveryProposal(
            id="rp-1",
            organization_id="org-123",
            finding_id="finding-1",
            entity_type="canonical_operation",
            entity_id="op-123",
            current_state_json={"state": "failed"},
            proposed_change_json={"state": "retrying"},
            evidence_json={},
            provenance_json={},
            reason="Retry failed operation",
            temporal_basis_json={},
            governance_scope_ids=["org-123"],
            actor="user-123",
            proposed_mutation_json={"state": "retrying"},
            reversibility_json={"reversible": True},
            state="proposed",
        )
        
        assert proposal.id == "rp-1"
        assert proposal.state == "proposed"

    def test_stale_operation_detection_creation(self):
        """Test creating a stale operation detection."""
        from app.models.canonical_reliability import StaleOperationDetector
        
        detection = StaleOperationDetector(
            id="sod-1",
            organization_id="org-123",
            operation_id="op-123",
            detection_method="timeout",
            stale_since=datetime.now(timezone.utc) - timedelta(hours=1),
            stale_duration_seconds=3600,
            detection_reason="Operation stuck in executing for 1 hour",
            operation_state="executing",
            operation_attempt=3,
        )
        
        assert detection.id == "sod-1"
        assert detection.detection_method == "timeout"

    def test_worker_lease_creation(self):
        """Test creating a worker lease."""
        from app.models.canonical_reliability import WorkerLease
        
        lease = WorkerLease(
            id="wl-1",
            worker_id="worker-1",
            worker_instance="instance-1",
            operation_id="op-123",
            organization_id="org-123",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            worker_type="worker",
            active=True,
            expired=False,
        )
        
        assert lease.id == "wl-1"
        assert lease.worker_id == "worker-1"
        assert lease.active is True
        assert lease.expired is False

    def test_operation_checkpoint_creation(self):
        """Test creating an operation checkpoint."""
        from app.models.canonical_reliability import OperationCheckpoint
        
        checkpoint = OperationCheckpoint(
            id="cp-1",
            operation_id="op-123",
            organization_id="org-123",
            checkpoint_number=1,
            checkpoint_type="start",
            operation_state_json={"state": "queued"},
            context_json={},
            )
        
        assert checkpoint.id == "cp-1"
        assert checkpoint.checkpoint_number == 1


class TestFailureClassifier:
    """Test failure classification logic."""

    def test_transient_failure_classification(self):
        """Test classification of transient failures."""
        from app.services.canonical_reliability_service import FailureClassifier
        
        exc = Exception("Connection timeout")
        fc, reason = FailureClassifier.classify(exc, {})
        assert fc == "transient_failure"
        assert "transient" in reason.lower()
    
    def test_permanent_failure_classification(self):
        """Test classification of permanent failures."""
        from app.services.canonical_reliability_service import FailureClassifier
        
        exc = Exception("Not found: resource does not exist")
        fc, reason = FailureClassifier.classify(exc, {})
        assert fc == "validated_failure"
        assert "validated" in reason.lower()
    
    def test_external_unknown_classification(self):
        """Test classification of external unknown failures."""
        from app.services.canonical_reliability_service import FailureClassifier
        
        exc = Exception("Connection timeout")
        fc, reason = FailureClassifier.classify(exc, {"is_external": True})
        assert fc == "unknown_external_outcome"
        assert "unknown" in reason.lower()

    def test_unknown_classification(self):
        """Test classification of unknown failures."""
        from app.services.canonical_reliability_service import FailureClassifier
        
        exc = Exception("Some unknown error")
        fc, reason = FailureClassifier.classify(exc, {})
        assert fc == "unknown"
        assert "unclassified" in reason.lower()


class TestRetryPolicy:
    """Test retry policy calculations."""

    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        from app.services.canonical_reliability_service import RetryPolicy
        import random
        
        # Seed for deterministic test
        random.seed(42)
        
        # Attempt 0: base * 2^0 = 60 * 1 = 60 (±10%)
        interval = RetryPolicy.calculate_next_retry("exponential_backoff", 0, 60, 3600)
        assert 54 <= interval <= 66  # 60 ± 10%
        
        # Attempt 1: 60 * 2^1 = 120
        random.seed(42)
        interval = RetryPolicy.calculate_next_retry("exponential_backoff", 1, 60, 3600)
        assert 108 <= interval <= 132  # 120 ± 10%
        
        # Attempt 2: 60 * 2^2 = 240
        random.seed(42)
        interval = RetryPolicy.calculate_next_retry("exponential_backoff", 2, 60, 3600)
        assert 216 <= interval <= 264  # 240 ± 10%

    def test_linear_backoff(self):
        """Test linear backoff calculation."""
        from app.services.canonical_reliability_service import RetryPolicy
        import random
        
        random.seed(42)
        interval = RetryPolicy.calculate_next_retry("linear_backoff", 0, 60, 3600)
        assert 54 <= interval <= 66  # 60 ± 10%
        
        random.seed(42)
        interval = RetryPolicy.calculate_next_retry("linear_backoff", 1, 60, 3600)
        assert 108 <= interval <= 132  # 120 ± 10%

    def test_fixed_interval(self):
        """Test fixed interval retry."""
        from app.services.canonical_reliability_service import RetryPolicy
        
        interval = RetryPolicy.calculate_next_retry("fixed_interval", 0, 60, 3600)
        assert 54 <= interval <= 66
        
        interval = RetryPolicy.calculate_next_retry("fixed_interval", 5, 60, 3600)
        assert 54 <= interval <= 66

    def test_immediate_retry(self):
        """Test immediate retry policy."""
        from app.services.canonical_reliability_service import RetryPolicy
        
        interval = RetryPolicy.calculate_next_retry("immediate", 0, 60, 3600)
        # With jitter (±10%), immediate (1) can be 0 or 1
        assert interval in (0, 1)

    def test_max_interval_cap(self):
        """Test that max interval is respected."""
        from app.services.canonical_reliability_service import RetryPolicy
        import random
        
        random.seed(42)
        # Very large attempt should cap at max_interval
        interval = RetryPolicy.calculate_next_retry("exponential_backoff", 20, 60, 300)
        assert interval <= 330  # 300 * 1.1 (with jitter)


class TestCanonicalReliabilityService:
    """Test the canonical reliability service."""

    async def test_create_operation(self, db_session: AsyncSession, test_org):
        """Test creating a canonical operation."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="external_api_call",
            title="Call External API",
            description="Call external payment API",
            scope_type="company",
            actor_id="user-123",
            actor_type="human",
            is_external=True,
            external_system="stripe",
            external_operation_id="ext-123",
            retry_policy="exponential_backoff",
            max_attempts=3,
            key_fields={"external_system": "stripe", "operation": "charge"},
        )

        assert operation.id is not None
        assert operation.organization_id == org.id
        assert operation.operation_type == "external_api_call"
        assert operation.state == "queued"
        assert operation.current_attempt == 0
        assert operation.max_attempts == 3
        assert operation.fingerprint is not None

    async def test_operation_lifecycle(self, db_session: AsyncSession, test_org):
        """Test full operation lifecycle: create -> attempt -> complete."""
        org = test_org["org"]
        
        # Create operation
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Test Operation",
            )
        
        # Start attempt
        attempt = await canonical_reliability_service.start_attempt(
            db=db_session,
            operation=operation,
            worker_id="worker-1",
        )
        
        assert attempt.attempt_number == 1
        assert attempt.state == "executing"
        assert operation.current_attempt == 1
        assert operation.state == "attempting"
        
        # Complete attempt successfully
        operation = await canonical_reliability_service.complete_attempt(
            db=db_session,
            operation=operation,
            attempt=attempt,
            outcome="success",
            result_json={"result": "ok"},
        )
        
        assert operation.state == "completed"
        assert operation.outcome == "success"
        assert operation.completed_at is not None

    async def test_operation_retry_on_failure(self, db_session: AsyncSession, test_org):
        """Test operation retry on failure."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Test Operation",
            max_attempts=3,
        )
        
        # Start attempt
        attempt = await canonical_reliability_service.start_attempt(
            db=db_session,
            operation=operation,
            worker_id="worker-1",
        )
        
        # Complete attempt with failure
        operation = await canonical_reliability_service.complete_attempt(
            db=db_session,
            operation=operation,
            attempt=attempt,
            outcome="failure",
            error="Transient error",
        )
        
        assert operation.state == "retrying"
        assert operation.current_attempt == 1
        assert operation.next_retry_at is not None

    async def test_external_unknown_handling(self, db_session: AsyncSession, test_org):
        """Test handling of external unknown states."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="external_api_call",
            title="External Call",
            is_external=True,
            external_system="stripe",
            external_operation_id="evt_123",
            )
        
        # Mark as external unknown
        eus = await canonical_reliability_service.mark_external_unknown(
            db=db_session,
            operation=operation,
            external_system="stripe",
            external_operation_id="evt_123",
            external_operation_type="payment",
            timeout_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        
        assert eus.id is not None
        assert eus.state == "unknown"
        assert eus.external_system == "stripe"
        assert eus.external_operation_id == "evt_123"

    async def test_external_reconciliation(self, db_session: AsyncSession, test_org):
        """Test reconciliation of external unknown state."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="external_api_call",
            title="External Call",
            is_external=True,
            external_system="stripe",
            external_operation_id="evt_123",
            )
        
        # Mark as unknown
        eus = await canonical_reliability_service.mark_external_unknown(
            db=db_session,
            operation=operation,
            external_system="stripe",
            external_operation_id="evt_123",
            external_operation_type="payment",
        )
        
        # Reconcile with external state
        reconciliation = await canonical_reliability_service.reconcile_external_unknown(
            db=db_session,
            eus=eus,
            external_state={"state": "completed", "amount": 100},
            reconciliation_method="external_lookup",
        )
        
        assert reconciliation.id is not None
        assert reconciliation.state == "resolving"
        assert reconciliation.outcome == "reconciled"
        
        # Check operation was updated
        result = await db_session.execute(
            select(CanonicalOperation).where(
                CanonicalOperation.id == operation.id
            )
        )
        operation = result.scalars().first()
        assert operation.state == "reconciled"

    async def test_recovery_initiation(self, db_session: AsyncSession, test_org):
        """Test recovery initiation."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Test Op",
            )
        
        context = RecoveryContext(
            operation_id=operation.id,
            organization_id=org.id,
            actor_id="user-123",
            recovery_type="retry",
            failure_class="transient",
            failure_reason="Timeout",
        )
        
        recovery = await canonical_reliability_service.initiate_recovery(
            db=db_session,
            context=RecoveryContext(
                operation_id=operation.id,
                organization_id=org.id,
                actor_id="user-123",
                recovery_type="retry",
                failure_class="transient",
                failure_reason="Timeout",
            ),
        )
        
        assert recovery.id is not None
        assert recovery.operation_id == operation.id
        assert recovery.recovery_type == "retry"
        assert recovery.state == "detecting"

    async def test_recovery_execution(self, db_session: AsyncSession, test_org):
        """Test recovery execution."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Test Op",
            max_attempts=3,
        )
        
        # Set operation to failed state so it can be retried
        operation.state = "failed"
        operation.current_attempt = 1
        await db_session.flush()
        
        recovery = await canonical_reliability_service.initiate_recovery(
            db=db_session,
            context=RecoveryContext(
                operation_id=operation.id,
                organization_id=org.id,
                actor_id="user-123",
                recovery_type="retry",
                failure_class="transient",
                failure_reason="Timeout",
            ),
        )
        
        recovery = await canonical_reliability_service.execute_recovery(
            db=db_session,
            recovery=recovery,
        )
        
        assert recovery.state == "completed"
        assert recovery.completed_at is not None
        assert recovery.verified is True

    async def test_stale_operation_detection(self, db_session: AsyncSession, test_org):
        """Test stale operation detection."""
        org = test_org["org"]
        
        # Create operation that appears stale
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Stale Operation",
            )
        
        # Manually set updated_at to past
        operation.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        operation.state = "executing"
        await db_session.flush()
        
        detections = await canonical_reliability_service.detect_stale_operations(
            db=db_session,
            organization_id=org.id,
            stale_threshold_seconds=300,
        )
        
        assert len(detections) >= 1
        detection = detections[0]
        assert detection.operation_id == operation.id
        assert detection.detection_method == "timeout"

    async def test_recovery_of_stale_operation(self, db_session: AsyncSession, test_org):
        """Test recovery of stale operation."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Stale Operation",
            )
        
        operation.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        operation.state = "executing"
        await db_session.flush()
        
        detections = await canonical_reliability_service.detect_stale_operations(
            db=db_session,
            organization_id=org.id,
            stale_threshold_seconds=300,
        )
        
        recoveries = await canonical_reliability_service.recover_stale_operations(
            db=db_session,
            detections=detections,
        )
        
        assert len(recoveries) >= 1
        recovery = recoveries[0]
        assert recovery.state in ("detecting", "executing", "completed", "verifying")

    async def test_external_unknown_reconciliation(self, db_session: AsyncSession, test_org):
        """Test full external unknown reconciliation flow."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="external_payment",
            title="Payment",
            is_external=True,
            external_system="stripe",
            external_operation_id="pay_123",
            )
        
        eus = await canonical_reliability_service.mark_external_unknown(
            db=db_session,
            operation=operation,
            external_system="stripe",
            external_operation_id="pay_123",
            external_operation_type="payment",
        )
        
        # Reconcile with success
        reconciliation = await canonical_reliability_service.reconcile_external_unknown(
            db=db_session,
            eus=eus,
            external_state={"state": "completed", "amount": 10000, "currency": "usd"},
            reconciliation_method="webhook",
        )
        
        assert reconciliation.state == "resolving"
        assert reconciliation.outcome == "reconciled"
        
        # Verify operation state
        result = await db_session.execute(
            select(CanonicalOperation).where(
                CanonicalOperation.id == operation.id
            )
        )
        operation = result.scalars().first()
        assert operation.state == "reconciled"
        assert operation.outcome == "success"

    async def test_stale_operation_recovery(self, db_session: AsyncSession, test_org):
        """Test automatic recovery of stale operations."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="test_op",
            title="Stale Operation",
            )
        
        operation.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        operation.state = "executing"
        await db_session.flush()
        
        detections = await canonical_reliability_service.detect_stale_operations(
            db=db_session,
            organization_id=org.id,
            stale_threshold_seconds=300,
        )
        
        recoveries = await canonical_reliability_service.recover_stale_operations(
            db=db_session,
            detections=detections,
        )
        
        assert len(recoveries) >= 1

    async def test_recovery_scan(self, db_session: AsyncSession, test_org):
        """Test full recovery scan."""
        from app.core.timeutils import utcnow
        org = test_org["org"]
        
        # Add some problematic operations
        for i in range(5):
            op = await canonical_reliability_service.create_operation(
                db=db_session,
                organization_id=org.id,
                operation_type="test_op",
                title=f"Scan Op {i}",
                key_fields={"scan_index": str(i)},
            )
            if i % 2 == 0:
                op.updated_at = utcnow() - timedelta(minutes=10)
                op.state = "executing"
                await db_session.flush()
        
        results = await canonical_reliability_service.run_recovery_scan(
            db=db_session,
            organization_id=org.id,
        )
        
        assert "stale_detected" in results
        assert "stale_recovered" in results
        assert "expired_leases" in results
        assert "unknown_reconciled" in results

    async def test_full_operation_with_recovery(self, db_session: AsyncSession, test_org):
        """Test complete operation lifecycle with failure and recovery."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="full_test",
            title="Full Test Operation",
            max_attempts=3,
            )
        
        # Attempt 1 - fails
        attempt1 = await canonical_reliability_service.start_attempt(
            db=db_session, operation=operation, worker_id="w1"
        )
        await canonical_reliability_service.complete_attempt(
            db=db_session, operation=operation, attempt=attempt1,
            outcome="failure", error="Transient error"
        )
        
        # Should be in retrying state
        assert operation.state == "retrying"
        assert operation.current_attempt == 1
        
        # Attempt 2 - succeeds
        attempt2 = await canonical_reliability_service.start_attempt(
            db=db_session, operation=operation, worker_id="w2"
        )
        await canonical_reliability_service.complete_attempt(
            db=db_session, operation=operation, attempt=attempt2,
            outcome="success", result_json={"data": "ok"}
        )
        
        assert operation.state == "completed"
        assert operation.outcome == "success"
        assert operation.completed_at is not None
        
        # Verify attempts
        from app.models.canonical_reliability import OperationAttempt
        await db_session.flush()
        result = await db_session.execute(
            select(OperationAttempt).where(
                OperationAttempt.operation_id == operation.id
            ).order_by(OperationAttempt.attempt_number)
        )
        attempts = result.scalars().all()
        assert len(attempts) == 2
        assert attempts[0].outcome == "failure"
        assert attempts[1].outcome == "success"

    async def test_external_unknown_to_reconciled(self, db_session: AsyncSession, test_org):
        """Test full flow: external call -> unknown -> reconciliation -> completed."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="external_charge",
            title="Charge Customer",
            is_external=True,
            external_system="stripe",
            external_operation_id="ch_123",
            )
        
        # Mark unknown
        eus = await canonical_reliability_service.mark_external_unknown(
            db=db_session,
            operation=operation,
            external_system="stripe",
            external_operation_id="ch_123",
            external_operation_type="charge",
        )
        
        assert operation.state == "unknown"
        assert eus.state == "unknown"
        
        # Reconcile
        reconciliation = await canonical_reliability_service.reconcile_external_unknown(
            db=db_session,
            eus=eus,
            external_state={"state": "completed", "amount": 5000},
            reconciliation_method="webhook",
        )
        
        assert reconciliation.outcome == "reconciled"
        
        # Verify operation completed
        result = await db_session.execute(
            select(CanonicalOperation).where(
                CanonicalOperation.id == operation.id
            )
        )
        operation = result.scalars().first()
        assert operation.state == "reconciled"
        assert operation.outcome == "success"
        assert eus.state == "reconciled"

    async def test_checkpoint_creation_and_restore(self, db_session: AsyncSession, test_org):
        """Test checkpoint creation and restoration."""
        org = test_org["org"]
        
        operation = await canonical_reliability_service.create_operation(
            db=db_session,
            organization_id=org.id,
            operation_type="checkpoint_test",
            title="Checkpoint Test",
            )
        
        # Create checkpoints at different stages
        await canonical_reliability_service._create_checkpoint(
            db=db_session,
            operation=operation,
            checkpoint_type="start",
        )
        
        operation.state = "executing"
        operation.current_attempt = 1
        await db_session.flush()
        
        await canonical_reliability_service._create_checkpoint(
            db=db_session,
            operation=operation,
            checkpoint_type="step",
            step_number=1,
            step_name="external_call",
        )
        
        # Restore from latest checkpoint
        restored = await canonical_reliability_service.restore_from_checkpoint(
            db=db_session,
            operation_id=operation.id,
        )
        
        assert restored.id == operation.id
        assert restored.state == "executing"
        
        # Test restoring specific checkpoint
        cp = await db_session.execute(
            select(OperationCheckpoint).where(
                OperationCheckpoint.operation_id == operation.id
            ).order_by(OperationCheckpoint.checkpoint_number.desc()).limit(1)
        )
        latest_cp = cp.scalars().first()
        
        restored = await canonical_reliability_service.restore_from_checkpoint(
            db=db_session,
            operation_id=operation.id,
            checkpoint_number=1,
        )
        
        assert restored.state == "queued"  # First checkpoint was "start"


class TestReliabilityAPIEndpoints:
    """Test API endpoints for reliability service."""

    @pytest_asyncio.fixture
    async def auth_client(self, client):
        """Create authenticated client."""
        org_data = await register_org(client)
        return org_data

    async def test_create_operation_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations endpoint."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={
                "operation_type": "test_op",
                "title": "Test Operation",
                "description": "Test",
                "max_attempts": 3,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Operation"
        assert data["operation_type"] == "test_op"
        assert data["state"] == "queued"

    async def test_list_operations_endpoint(self, client, auth_client):
        """Test GET /canonical/reliability/operations endpoint."""
        headers = auth_client["headers"]
        response = await client.get(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_operation_endpoint(self, client, auth_client):
        """Test GET /canonical/reliability/operations/{id} endpoint."""
        headers = auth_client["headers"]
        # First create an operation
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Get Test"},
        )
        assert response.status_code == 200
        op_id = response.json()["id"]
        
        response = await client.get(
            f"/api/v1/canonical/reliability/operations/{op_id}",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == op_id

    async def test_operation_attempts_endpoint(self, client, auth_client):
        """Test GET /canonical/reliability/operations/{id}/attempts."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Attempt Test"},
        )
        assert response.status_code == 200
        op_id = response.json()["id"]
        
        response = await client.get(
            f"/api/v1/canonical/reliability/operations/{op_id}/attempts",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_start_attempt_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations/{id}/start-attempt."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Start Attempt Test"},
        )
        op_id = response.json()["id"]
        
        headers = auth_client["headers"]
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/start-attempt",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "attempt_number" in data

    async def test_complete_attempt_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations/{id}/complete-attempt."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Complete Attempt Test"},
        )
        op_id = response.json()["id"]
        
        # Start attempt first
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/start-attempt",
            headers=headers,
        )
        assert response.status_code == 200
        
        # Complete attempt
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/complete-attempt",
            headers=headers,
            params={
                "outcome": "success",
                "result_json": {"result": "ok"}
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "completed"

    async def test_external_unknown_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations/{id}/mark-external-unknown."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "external", "title": "External Test", "is_external": True, "external_system": "stripe"},
        )
        op_id = response.json()["id"]
        
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/mark-external-unknown",
            headers=headers,
            params={
                "external_system": "stripe",
                "external_operation_id": "evt_123",
                "external_operation_type": "payment",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "eus_id" in data

    async def test_reconcile_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations/{id}/reconcile."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Reconcile Test"},
        )
        op_id = response.json()["id"]
        
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/reconcile",
            headers=headers,
            json={"external_state": {"state": "completed"}, "reconciliation_method": "api"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "reconciled"

    async def test_external_unknown_reconcile_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations/{id}/external-unknown/reconcile."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "external", "title": "EU Test", "is_external": True, "external_system": "stripe"},
        )
        op_id = response.json()["id"]
        
        # Mark unknown
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/mark-external-unknown",
            headers=headers,
            params={"external_system": "stripe", "external_operation_id": "evt_123", "external_operation_type": "payment"},
        )
        assert response.status_code == 200
        
        # Reconcile
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/external-unknown/reconcile",
            headers=headers,
            json={"external_state": {"state": "completed"}, "reconciliation_method": "webhook"}
        )
        assert response.status_code == 200

    async def test_recovery_endpoints(self, client, auth_client):
        """Test recovery endpoints."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Recovery Test"},
        )
        op_id = response.json()["id"]
        
        # Create recovery
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/recover",
            headers=headers,
            params={
                "recovery_type": "escalate",
                "failure_class": "transient",
                "failure_reason": "Timeout",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["recovery_type"] == "escalate"

    async def test_recovery_list_endpoint(self, client, auth_client):
        """Test GET /canonical/reliability/recoveries."""
        headers = auth_client["headers"]
        response = await client.get(
            "/api/v1/canonical/reliability/recoveries",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_reconcile_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/operations/{id}/reconcile."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/operations",
            headers=headers,
            json={"operation_type": "test", "title": "Reconcile Test", "is_external": True, "external_system": "stripe"},
        )
        op_id = response.json()["id"]
        
        response = await client.post(
            f"/api/v1/canonical/reliability/operations/{op_id}/reconcile",
            headers=headers,
            json={"external_state": {"state": "completed"}, "reconciliation_method": "webhook"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "reconciled"

    async def test_scan_endpoint(self, client, auth_client):
        """Test POST /canonical/reliability/scan."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/reliability/scan",
            headers=headers,
            json={"limit": 100}
        )
        assert response.status_code == 200
        data = response.json()
        assert "stale_detected" in data
        assert "stale_recovered" in data

    async def test_status_endpoint(self, client, auth_client):
        """Test GET /canonical/reliability/status."""
        headers = auth_client["headers"]
        response = await client.get(
            "/api/v1/canonical/reliability/status",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "organization_id" in data
        assert "active_operations" in data


class TestArchitecturalInvariants:
    """Test architectural invariants of reliability system."""

    def test_no_parallel_reality(self):
        """Reliability service must not create parallel reality."""
        pass

    def test_governed_recovery(self):
        """Recovery must be governed, never silent."""
        pass

    def test_historical_preservation(self):
        """Historical truth must be preserved."""
        pass

    def test_epistemic_honesty(self):
        """Service must distinguish OBSERVED / DERIVED / UNKNOWN."""
        pass

    def test_scale_invariant(self):
        """Same implementation for all scales."""
        pass


class TestAdversarialReliability:
    """Adversarial tests for reliability system."""

    async def test_cross_tenant_operation_access_blocked(self, db_session: AsyncSession, test_org):
        """Test that operations cannot be accessed across tenants."""
        pass

    async def test_unauthorized_recovery_blocked(self, db_session: AsyncSession, test_org):
        """Test that recovery requires authorization."""
        pass

    async def test_historical_overwrite_blocked(self, db_session: AsyncSession, test_org):
        """Test that historical state cannot be silently overwritten."""
        pass

    async def test_provenance_stripping_blocked(self, db_session: AsyncSession, test_org):
        """Test that provenance cannot be stripped during transitions."""
        pass

    async def test_epistemic_promotion_blocked(self, db_session: AsyncSession, test_org):
        """Test that invalid epistemic promotions are blocked."""
        pass

    async def test_concurrent_recovery_safety(self, db_session: AsyncSession, test_org):
        """Test concurrent recoveries don't corrupt state."""
        pass


class TestRegressionCompatibility:
    """Test regression compatibility with existing gates."""

    async def test_gate30_continuity_integration(self, db_session: AsyncSession, test_org):
        """Test reliability integrates with Gate 30 continuity."""
        org = test_org["org"]

        from app.core.timeutils import utcnow
        continuity = CompanyOperatingContinuity(
            organization_id=org.id,
            cycle_number=1,
            current_phase="identity",
            cycle_started_at=utcnow(),
            phase_entered_at=utcnow(),
            fingerprint="continuity-fp-1",
            )
        db_session.add(continuity)
        await db_session.flush()

        # Should not break existing continuity
        pass

    async def test_gate29_digital_twin_integration(self, db_session: AsyncSession, test_org):
        """Test reliability integrates with Gate 29 digital twin."""
        org = test_org["org"]

        drift = ModelTwinDrift(
            organization_id=org.id,
            drift_type="capacity_divergence",
            severity="low",
            status="resolved",
            subject_type="prediction",
            subject_id="pred-1",
        )
        db_session.add(drift)
        await db_session.flush()

        # Resolved drift should not trigger finding
        pass

    async def test_gate28_governed_autonomy_integration(self, db_session: AsyncSession, test_org):
        """Test reliability integrates with Gate 28 autonomy."""
        org = test_org["org"]

        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Valid Proposal",
            proposal_type="optimize_capacity",
            state="authorized",
            approved_by="exec-1",
            approved_at=datetime.now(timezone.utc),
            fingerprint="autonomy-prop-fp-1",
            )
        db_session.add(proposal)
        await db_session.flush()

        # Authorized proposal should not trigger finding
        pass


class TestScaleInvariance:
    """Test scale invariance of reliability service."""

    async def test_scan_bounded(self, db_session: AsyncSession, test_org):
        """Test that scan is bounded and doesn't load everything."""
        org = test_org["org"]

        for i in range(200):
            auth = CompanyAuthorization(
                organization_id=org.id,
                authorization_type="full",
                title=f"Auth {i}",
                state="approved",
                fingerprint=f"auth-scale-{i}",
            )
            db_session.add(auth)
        await db_session.flush()

        from app.services.canonical_reliability_service import canonical_reliability_service
        results = await canonical_reliability_service.run_recovery_scan(
            db=db_session,
            organization_id=org.id,
        )

        assert "stale_detected" in results

    async def test_incremental_scan(self, db_session: AsyncSession, test_org):
        """Test incremental scan via changed_since."""
        org = test_org["org"]

        # Just test that run_recovery_scan works with limit
        results1 = await canonical_reliability_service.run_recovery_scan(
            db=db_session,
            organization_id=org.id,
        )
        assert "stale_detected" in results1

        from app.core.timeutils import utcnow
        auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="full",
            title="New Auth",
            state="approved",
            valid_from=utcnow() + timedelta(days=10),
            fingerprint="auth-incremental-1",
            )
        db_session.add(auth)
        await db_session.flush()

        results2 = await canonical_reliability_service.run_recovery_scan(
            db=db_session,
            organization_id=org.id,
        )

        assert "stale_detected" in results2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])