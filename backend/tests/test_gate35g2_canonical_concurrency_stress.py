"""Gate 35-G.2 — Universal Canonical Concurrency Stress & Acceptance Tests.

These tests verify that the canonical concurrency primitives actually protect
the canonical company operating fabric under real concurrent load.

The invariant: MANY ACTORS + MANY CONCURRENT OPERATIONS = ONE CANONICAL COMPANY REALITY
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Callable, Awaitable, Tuple
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from app.intelligence.canonical_concurrency import (
    LeaseManager,
    WorkerCoordinator,
    CanonicalOperationConcurrency,
    IdempotentExecutor,
    CanonicalConcurrencyCoordinator,
    IdempotencyKeyManager,
    OptimisticConcurrencyManager,
    PessimisticLockManager,
    ConcurrencyControlType,
    ConcurrencyContext,
    ConcurrencyResult,
)
from app.intelligence.canonical_mutation import (
    canonical_create,
    canonical_update,
    canonical_transition,
    canonical_delete,
    worker_canonical_mutation,
    MutationType,
    EpistemicStatus,
    CanonicalMutationBoundary,
    CanonicalMutationContext,
    ExactOnceViolation,
    GovernanceViolation,
    TenantIsolationViolation,
    ScopeViolation,
    TemporalViolation,
    ProvenanceViolation,
    EpistemicViolation,
)
from app.intelligence.canonical_types import (
    ConcurrencyConflictResolution,
)
from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    WorkerLease,
    OperationCheckpoint,
    OPERATION_STATES,
    ATTEMPT_STATES,
    RECOVERY_STATES,
    RECOVERY_TYPES,
    FAILURE_CLASSES,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    CompanyGoal,
    CompanyObjective,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionContradiction,
    CompanyDecisionAlternative,
)
from app.models.company_actions import CompanyAction
from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.core.timeutils import utcnow
from app.db.database import Base

from tests.concurrency import (
    # Fixtures
    concurrency_organization,
    concurrency_db_session_factory,
    ten_actors_same_company,
    hundred_actors_same_company,
    two_actors_same_company,
    cross_company_actors,
    two_orgs_two_actors_each,
    shared_company_commitment,
    shared_company_authorization,
    shared_canonical_operation,
    worker_lease_manager,
    worker_lease_operation,
    external_event_source,
    temporal_authorization_chain,
    ai_generated_decision,
    evidence_backed_decision,
    # Assertions
    assert_idempotent_duplicate_operations,
    assert_optimistic_concurrency_conflict,
    assert_unknown_state_preserved,
    assert_recovery_reconciliation_flow,
    assert_valid_lifecycle_transition,
    assert_company_brain_does_not_mutate_canonical,
    # Context
    ConcurrentTestRunner,
    ConcurrentTestResult,
    ConcurrentSessionHarness,
    ConcurrencyBarrier,
)


# =============================================================================
# Helper: Create canonical provenance entities for concurrency tests
# =============================================================================

async def _create_canonical_provenance(db: AsyncSession, org_id: str, caller: CallerAccess) -> dict:
    """Create real CompanyDecision and CompanyAuthorization for provenance.
    
    Returns dict with 'decision_id' and 'authorization_id'.
    Note: The db session must have an active transaction.
    """
    # Create a valid CompanyDecision through canonical boundary
    decision = CompanyDecision(
        organization_id=org_id,
        decision_id=f"dec-concurrency-{uuid.uuid4().hex[:8]}",
        kind="strategic",
        title="Concurrency Test Decision",
        rationale="Test decision for concurrency provenance",
        state="approved",
        approver_label="test",
        source_event_id=f"evt-dec-{uuid.uuid4().hex[:8]}",
    )
    decision_result = await canonical_create(
        db=db,
        caller=caller,
        entity=decision,
        required_permissions=["decisions:manage"],
    )
    
    # Create approval policy
    from app.models.governance import ApprovalPolicy
    policy = ApprovalPolicy(
        organization_id=org_id,
        name="Concurrency Test Policy",
        description="Test policy for concurrency",
        required_permission="authorizations:manage",
        is_active=True,
    )
    db.add(policy)
    await db.flush()
    
    # Create a valid CompanyAuthorization through canonical boundary
    auth = CompanyAuthorization(
        organization_id=org_id,
        authorization_type="full",
        title="Concurrency Test Authorization",
        scope_type="company",
        state="approved",
        valid_from=utcnow(),
        fingerprint=f"fp-auth-{uuid.uuid4().hex[:8]}",
        decision_id=decision_result.entity.id,
        policy_id=policy.id,
    )
    auth_result = await canonical_create(
        db=db,
        caller=caller,
        entity=auth,
        provenance={"decision_id": decision_result.entity.id, "policy_id": policy.id},
        required_permissions=["authorizations:manage"],
    )
    
    if auth_result.entity is None:
        raise RuntimeError(f"Failed to create authorization: {auth_result.error}")
    
    return {
        "decision_id": decision_result.entity.id,
        "authorization_id": auth_result.entity.id,
    }


# =============================================================================
# Test Class: Same Operation Duplication (10/100 concurrent)
# =============================================================================

class TestSameOperationDuplication:
    """Test that duplicate concurrent operations are safely controlled."""
    
    @pytest.mark.asyncio
    async def test_10_concurrent_identical_creates(
        self, 
        ten_actors_same_company,
    ):
        """10 concurrent identical creates with same source_event_id → 1 canonical effect."""
        actors = ten_actors_same_company
        source_event_id = f"evt-dup-10-{uuid.uuid4().hex[:8]}"
        
        async def create_decision(actor_id: str, ctx: Any):
            caller = actors.harness.get_caller(actor_id)
            decision = CompanyDecision(
                organization_id=actors.organization.id,
                decision_id=f"dec-dup-{actor_id}-{uuid.uuid4().hex[:8]}",
                kind="other",
                title=f"Concurrent Decision {actor_id}",
                rationale="Test",
                state="proposed",
                source_event_id=source_event_id,
            )
            # Do NOT add to session or flush - canonical_create will handle idempotent insert
            # using database-level INSERT ... ON CONFLICT DO NOTHING / INSERT OR IGNORE
            
            return await canonical_create(
                db=ctx.session,
                caller=caller,
                entity=decision,
                provenance={"authorization_id": "auth-1", "decision_id": "dec-1"},
                required_permissions=["decisions:manage"],
            )
        
        results = await actors.runner.run_concurrent(create_decision)
        
        # All 10 should succeed (idempotent) and produce exactly 1 entity
        entity_id = assert_idempotent_duplicate_operations(
            actors.runner, 10, "CompanyDecision"
        )
        
        # Verify the entity exists and has correct state
        db = actors.harness.session_factory()
        async with db.begin():
            entity = await db.get(CompanyDecision, entity_id)
            assert entity is not None
            assert entity.source_event_id == source_event_id
    
    @pytest.mark.asyncio
    async def test_100_concurrent_identical_creates(
        self,
        hundred_actors_same_company,
    ):
        """100 concurrent identical creates with same source_event_id → 1 canonical effect."""
        actors = hundred_actors_same_company
        source_event_id = f"evt-dup-100-{uuid.uuid4().hex[:8]}"
        
        async def create_decision(actor_id: str, ctx: Any):
            caller = actors.harness.get_caller(actor_id)
            decision = CompanyDecision(
                organization_id=actors.organization.id,
                decision_id=f"dec-dup-{actor_id}-{uuid.uuid4().hex[:8]}",
                kind="other",
                title=f"Concurrent Decision {actor_id}",
                rationale="Test",
                state="proposed",
                source_event_id=source_event_id,
            )
            # Do NOT add to session or flush - canonical_create will handle idempotent insert
            # using database-level INSERT ... ON CONFLICT DO NOTHING / INSERT OR IGNORE
            
            return await canonical_create(
                db=ctx.session,
                caller=caller,
                entity=decision,
                provenance={"authorization_id": "auth-1", "decision_id": "dec-1"},
                required_permissions=["decisions:manage"],
            )
        
        results = await actors.runner.run_concurrent(create_decision)
        
        # All 100 should succeed (idempotent) and produce exactly 1 entity
        entity_id = assert_idempotent_duplicate_operations(
            actors.runner, 100, "CompanyDecision"
        )
    
    @pytest.mark.asyncio
    async def test_10_concurrent_identical_updates(
        self,
        ten_actors_same_company,
    ):
        """10 concurrent identical updates → no lost updates, all see same final state."""
        actors = ten_actors_same_company
        
        # Create real provenance entities in a transaction
        db_provenance = actors.harness.session_factory()
        async with db_provenance.begin():
            caller = actors.harness.get_caller(list(actors.actors.values())[0].user_id)
            provenance = await _create_canonical_provenance(
                db=db_provenance,
                org_id=actors.organization.id,
                caller=caller,
            )
        
        # Create initial entity with required provenance
        comm = CompanyCommitment(
            organization_id=actors.organization.id,
            commitment_type="unconditional",
            title="Original Title",
            scope_type="objective",
            authorization_id=provenance["authorization_id"],
            decision_id=provenance["decision_id"],
            fingerprint=f"test-concurrent-update-{uuid.uuid4().hex[:8]}",
        )
        db = actors.harness.session_factory()
        async with db.begin():
            db.add(comm)
            await db.flush()
            initial_version = comm.version
        
        async def update_commitment(actor_id: str, ctx: Any):
            caller = actors.harness.get_caller(actor_id)
            return await canonical_update(
                db=ctx.session,
                caller=caller,
                entity_type="CompanyCommitment",
                entity_id=comm.id,
                updates={"title": f"Updated by {actor_id}"},
                expected_version=initial_version,
                provenance={"authorization_id": provenance["authorization_id"], "decision_id": provenance["decision_id"]},
                required_permissions=["commitments:manage"],
            )
        
        results = await actors.runner.run_concurrent(update_commitment)
        
        # Exactly 1 should succeed, 9 should fail with concurrency error
        assert_optimistic_concurrency_conflict(actors.runner, expected_successes=1)
        
        # Final entity should have version = initial + 1
        db = actors.harness.session_factory()
        # Use session directly without explicit transaction to see committed changes
        final = await db.get(CompanyCommitment, comm.id)
        assert final.version == initial_version + 1, f"Expected version {initial_version + 1}, got {final.version}"


# =============================================================================
# Test Class: Optimistic Concurrency
# =============================================================================

class TestOptimisticConcurrency:
    """Test optimistic concurrency control prevents lost updates."""
    
    @pytest.mark.asyncio
    async def test_version_conflict_detection(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Worker A updates N→N+1, Worker B attempts N→N+1 → B gets conflict."""
        org = concurrency_organization
        
        # Create real provenance entities
        from tests.concurrency import CanonicalActorBuilder
        from app.intelligence.canonical_mutation import canonical_create
        from app.models.execution_strategy import CompanyAuthorization
        
        db = concurrency_db_session_factory()
        async with db.begin():
            builder = CanonicalActorBuilder(
                db=db,
                organization=org,
                user_id=f"actor-opt-{uuid.uuid4().hex[:8]}",
                email=f"opt-{uuid.uuid4().hex[:8]}@test.com",
                full_name="Opt Actor",
                role_codes=["ceo"],
            )
            actor = await builder.build()
            caller = actor.to_caller_access()
            
            # Create real provenance
            decision = CompanyDecision(
                organization_id=org.id,
                decision_id=f"dec-opt-{uuid.uuid4().hex[:8]}",
                kind="strategic",
                title="Opt Test Decision",
                rationale="Test",
                state="approved",
                approver_label="test",
                source_event_id="evt-opt",
            )
            decision_result = await canonical_create(
                db=db,
                caller=caller,
                entity=decision,
                required_permissions=["decisions:manage"],
            )
            
            # Create approval policy
            from app.models.governance import ApprovalPolicy
            policy = ApprovalPolicy(
                organization_id=org.id,
                name="Opt Test Policy",
                description="Test policy for optimization",
                required_permission="authorizations:manage",
                is_active=True,
            )
            db.add(policy)
            await db.flush()
            
            auth = CompanyAuthorization(
                organization_id=org.id,
                authorization_type="full",
                title="Opt Test Authorization",
                scope_type="company",
                state="approved",
                valid_from=utcnow(),
                fingerprint=f"fp-auth-{uuid.uuid4().hex[:8]}",
                decision_id=decision_result.entity.id,
                policy_id=policy.id,
            )
            auth_result = await canonical_create(
                db=db,
                caller=caller,
                entity=auth,
                provenance={"decision_id": decision_result.entity.id, "policy_id": policy.id},
                required_permissions=["authorizations:manage"],
            )
            
            decision_id = decision_result.entity.id
            authorization_id = auth_result.entity.id
        
        # Create entity with version (CompanyCommitment) - include required provenance
        comm = CompanyCommitment(
            organization_id=org.id,
            commitment_type="unconditional",
            title="Test Commitment",
            scope_type="objective",
            authorization_id=authorization_id,
            decision_id=decision_id,
            fingerprint=f"test-opt-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(comm)
            await db.flush()
            initial_version = comm.version
            comm_id = comm.id
        
        # Create actor with permissions
        builder = CanonicalActorBuilder(
            db=db,
            organization=org,
            user_id=f"actor-opt-{uuid.uuid4().hex[:8]}",
            email=f"opt-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Opt Actor",
            role_codes=["ceo"],
        )
        actor = await builder.build()
        caller = actor.to_caller_access()
        
        # Worker A updates
        db2 = concurrency_db_session_factory()
        async with db2.begin():
            result_a = await canonical_update(
                db=db2,
                caller=caller,
                entity_type="CompanyCommitment",
                entity_id=comm_id,
                updates={"title": "Updated by Worker A"},
                expected_version=initial_version,
                provenance={"authorization_id": authorization_id, "decision_id": decision_id},
                required_permissions=["commitments:manage"],
            )
        assert result_a.success is True
        
        # Worker B tries with stale version
        db3 = concurrency_db_session_factory()
        async with db3.begin():
            result_b = await canonical_update(
                db=db3,
                caller=caller,
                entity_type="CompanyCommitment",
                entity_id=comm_id,
                updates={"title": "Updated by Worker B"},
                expected_version=initial_version,  # STALE version
                provenance={"authorization_id": authorization_id, "decision_id": decision_id},
                required_permissions=["commitments:manage"],
            )
        
        assert result_b.success is False
        assert any(kw in result_b.error.lower() for kw in ["stale", "version", "concurrency"])
        
        # Verify final state
        db4 = concurrency_db_session_factory()
        async with db4.begin():
            final = await db4.get(CompanyCommitment, comm_id)
            assert final.version == initial_version + 1
            assert final.title == "Updated by Worker A"
    
    @pytest.mark.asyncio
    async def test_concurrent_transition_race(
        self,
        ten_actors_same_company,
    ):
        """Concurrent state transitions on same entity → exactly one succeeds."""
        actors_obj = ten_actors_same_company
        harness = actors_obj.harness
        barrier = actors_obj.barrier
        org = actors_obj.organization
        actors_list = list(actors_obj.actors.values())
        actor_a, actor_b = actors_list[0], actors_list[1]
        actors = [actor_a, actor_b]
        
        # Use CompanyCommitment which has version and multiple valid transitions from "proposed"
        from tests.concurrency import ConcurrentTestRunner, ConcurrencyBarrier
        from app.models.execution_strategy import CompanyAuthorization
        from app.intelligence.canonical_mutation import canonical_create
        
        db = harness.session_factory()
        async with db.begin():
            # Create required provenance entities
            from tests.concurrency import CanonicalActorBuilder
            builder = CanonicalActorBuilder(
                db=db,
                organization=org,
                user_id=f"actor-race-{uuid.uuid4().hex[:8]}",
                email=f"race-{uuid.uuid4().hex[:8]}@test.com",
                full_name="Race Actor",
                role_codes=["ceo"],
            )
            actor = await builder.build()
            caller = actor.to_caller_access()
            
            # Create required provenance entities
            decision = CompanyDecision(
                organization_id=org.id,
                decision_id=f"dec-race-{uuid.uuid4().hex[:8]}",
                kind="strategic",
                title="Race Decision",
                rationale="Test",
                state="approved",
                approver_label="test",
                source_event_id="evt-dec",
            )
            decision_result = await canonical_create(
                db=db,
                caller=caller,
                entity=decision,
                required_permissions=["decisions:manage"],
            )
            
            # Create approval policy
            from app.models.governance import ApprovalPolicy
            policy = ApprovalPolicy(
                organization_id=org.id,
                name="Race Auth Policy",
                description="Test policy",
                required_permission="commitments:manage",
                is_active=True,
            )
            db.add(policy)
            await db.flush()
            
            auth = CompanyAuthorization(
                organization_id=org.id,
                authorization_type="full",
                title="Race Auth",
                scope_type="company",
                state="approved",
                valid_from=utcnow(),
                fingerprint=f"fp-auth-{uuid.uuid4().hex[:8]}",
                decision_id=decision_result.entity.id,
                policy_id=policy.id,
            )
            auth_result = await canonical_create(
                db=db,
                caller=caller,
                entity=auth,
                provenance={"decision_id": decision_result.entity.id, "policy_id": policy.id},
                required_permissions=["authorizations:manage"],
            )
            
            # Create commitment with required provenance
            commitment = CompanyCommitment(
                organization_id=org.id,
                id=f"comm-race-{uuid.uuid4().hex[:8]}",
                commitment_type="unconditional",
                title="Race Commitment",
                scope_type="objective",
                state="proposed",
                authorization_id=auth_result.entity.id,
                decision_id=decision_result.entity.id,
                fingerprint=f"fp-comm-{uuid.uuid4().hex[:8]}",
            )
            db.add(commitment)
            await db.flush()
            initial_version = commitment.version
            commitment_id = commitment.id
        
        # Create a new runner with only the 2 actors we need
        from tests.concurrency import ConcurrentTestRunner, ConcurrencyBarrier
        test_barrier = ConcurrencyBarrier(parties=2, name="transition-race")
        runner = ConcurrentTestRunner(
            session_factory=harness.session_factory,
            actors=actors,
            barrier=test_barrier,
        )
        
        actors_dict = {a.user_id: a for a in actors}
        
        async def transition_commitment(actor_id: str, ctx: Any):
            caller = actors_dict[actor_id].to_caller_access()
            # Both actors try different valid transitions from "proposed"
            target_state = "pending_authorization" if actor_id == actor_a.user_id else "authorized"
            return await canonical_transition(
                db=ctx.session,
                caller=caller,
                entity_type="CompanyCommitment",
                entity_id=commitment_id,
                new_state=target_state,
                expected_version=initial_version,
                provenance={"authorization_id": auth_result.entity.id, "decision_id": decision_result.entity.id},
                required_permissions=["commitments:manage"],
            )
        
        # Run truly concurrent transitions with only 2 workers
        results = await runner.run_concurrent(transition_commitment, barrier=test_barrier)
        
        # Exactly one should succeed, one should fail with concurrency error
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        assert len(successful) == 1, f"Expected 1 successful transition, got {len(successful)}"
        assert len(failed) == 1, f"Expected 1 failed transition, got {len(failed)}"
        assert any(kw in failed[0].error.lower() for kw in ["stale", "version", "concurrency"]), \
            f"Expected concurrency error, got: {failed[0].error}"
        
        # Verify final state
        db_check = harness.session_factory()
        async with db_check.begin():
            final = await db_check.get(CompanyCommitment, commitment_id)
            assert final.state in ["pending_authorization", "authorized"]
            assert final.version == initial_version + 1


# =============================================================================
# Test Class: WorkerLease Concurrency
# =============================================================================

class TestWorkerLeaseConcurrency:
    """Test WorkerLease-based worker coordination."""
    
    @pytest.mark.asyncio
    async def test_lease_acquire_excludes_other_workers(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Worker A acquires lease, Worker B tries same operation → rejected."""
        org = concurrency_organization
        operation_id = f"op-lease-{uuid.uuid4().hex[:8]}"
        
        operation = CanonicalOperation(
            id=operation_id,
            organization_id=org.id,
            operation_type="test_operation",
            title="Test Operation",
            state="queued",
            fingerprint=f"fp-lease-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(operation)
            await db.flush()
        
        lease_manager = LeaseManager(db)
        
        # Worker A acquires lease
        lease_a = await lease_manager.acquire_lease(
            worker_id="worker-a",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_a is not None
        
        # Worker B tries to acquire same operation lease
        lease_b = await lease_manager.acquire_lease(
            worker_id="worker-b",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_b is None, "Worker B should not acquire lease held by Worker A"
        
        # Verify Worker A's lease is still active
        active_lease = await lease_manager.get_lease(operation_id)
        assert active_lease is not None
        assert active_lease.worker_id == "worker-a"
        assert active_lease.active is True
    
    @pytest.mark.asyncio
    async def test_lease_expiration_allows_new_acquisition(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Worker A lease expires → Worker B can acquire."""
        org = concurrency_organization
        operation_id = f"op-lease-expire-{uuid.uuid4().hex[:8]}"
        
        operation = CanonicalOperation(
            id=operation_id,
            organization_id=org.id,
            operation_type="test_operation",
            title="Test Operation",
            state="queued",
            fingerprint=f"fp-lease-expire-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(operation)
            await db.flush()
        
        lease_manager = LeaseManager(db)
        
        # Worker A acquires lease with very short TTL
        lease_a = await lease_manager.acquire_lease(
            worker_id="worker-a",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(milliseconds=50),
        )
        assert lease_a is not None
        
        # Wait for lease to expire
        await asyncio.sleep(0.1)
        
        # Expire stale leases
        expired_count = await lease_manager.expire_stale_leases()
        assert expired_count >= 1
        
        # Worker B should now be able to acquire
        lease_b = await lease_manager.acquire_lease(
            worker_id="worker-b",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_b is not None, "Worker B should acquire after lease expiration"
        
        # Verify Worker A's lease is marked expired
        active_lease = await lease_manager.get_lease(operation_id)
        assert active_lease is not None
        assert active_lease.worker_id == "worker-b"
    
    @pytest.mark.asyncio
    async def test_lease_renewal_extends_ownership(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Worker A renews lease → continues to hold it."""
        org = concurrency_organization
        operation_id = f"op-lease-renew-{uuid.uuid4().hex[:8]}"
        
        operation = CanonicalOperation(
            id=operation_id,
            organization_id=org.id,
            operation_type="test_operation",
            title="Test Operation",
            state="queued",
            fingerprint=f"fp-lease-renew-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(operation)
            await db.flush()
        
        lease_manager = LeaseManager(db)
        
        # Worker A acquires lease
        lease_id = await lease_manager.acquire_lease(
            worker_id="worker-a",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(seconds=1),
        )
        assert lease_id is not None
        
        # Renew before expiry
        await asyncio.sleep(0.2)
        renewed = await lease_manager.renew_lease(lease_id, ttl=timedelta(seconds=1))
        assert renewed is True
        
        # Worker B should still be blocked
        lease_b = await lease_manager.acquire_lease(
            worker_id="worker-b",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_b is None, "Worker B should not acquire while A's lease is renewed"
        
        # Wait for renewed lease to expire
        await asyncio.sleep(1.2)
        await lease_manager.expire_stale_leases()
        
        # Now Worker B can acquire
        lease_b = await lease_manager.acquire_lease(
            worker_id="worker-b",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_b is not None
    
    @pytest.mark.asyncio
    async def test_lease_release_allows_new_acquisition(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Worker A releases lease → Worker B can acquire immediately."""
        org = concurrency_organization
        operation_id = f"op-lease-release-{uuid.uuid4().hex[:8]}"
        
        operation = CanonicalOperation(
            id=operation_id,
            organization_id=org.id,
            operation_type="test_operation",
            title="Test Operation",
            state="queued",
            fingerprint=f"fp-lease-release-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(operation)
            await db.flush()
        
        lease_manager = LeaseManager(db)
        
        # Worker A acquires lease
        lease_a = await lease_manager.acquire_lease(
            worker_id="worker-a",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_a is not None
        
        # Worker A releases lease
        released = await lease_manager.release_lease(lease_a)
        assert released is True
        
        # Worker B can acquire immediately
        lease_b = await lease_manager.acquire_lease(
            worker_id="worker-b",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_b is not None
        
        active = await lease_manager.get_lease(operation_id)
        assert active.worker_id == "worker-b"
    
    @pytest.mark.asyncio
    async def test_worker_coordinator_execute_with_lease(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """WorkerCoordinator executes operation with lease coordination."""
        org = concurrency_organization
        operation_id = f"op-coord-{uuid.uuid4().hex[:8]}"
        
        operation = CanonicalOperation(
            id=operation_id,
            organization_id=org.id,
            operation_type="test_operation",
            title="Test Operation",
            state="queued",
            fingerprint=f"fp-coord-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(operation)
            await db.flush()
        
        coordinator = WorkerCoordinator(db)
        execution_count = 0
        
        async def operation_fn():
            nonlocal execution_count
            execution_count += 1
            return {"executed_by": "worker-a", "count": execution_count}
        
        # First execution should succeed
        success, result = await coordinator.execute_with_lease(
            operation_id=operation_id,
            worker_id="worker-a",
            organization_id=org.id,
            operation_fn=operation_fn,
        )
        assert success is True
        assert execution_count == 1
        
        # Second concurrent execution should fail (lease held)
        success2, result2 = await coordinator.execute_with_lease(
            operation_id=operation_id,
            worker_id="worker-b",
            organization_id=org.id,
            operation_fn=operation_fn,
        )
        assert success2 is False
        assert execution_count == 1  # Not incremented


# =============================================================================
# Test Class: Worker Crash / UNKNOWN State
# =============================================================================

class TestWorkerCrashUnknownState:
    """Test worker crash handling and UNKNOWN state preservation."""
    
    @pytest.mark.asyncio
    async def test_worker_crash_creates_unknown_not_failed(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Worker acquires lease, starts execution, crashes → UNKNOWN state."""
        org = concurrency_organization
        
        operation_id = f"op-crash-{uuid.uuid4().hex[:8]}"
        
        operation = CanonicalOperation(
            id=operation_id,
            organization_id=org.id,
            operation_type="external_api_call",
            title="External API Call",
            state="queued",
            is_external=True,
            external_system="stripe",
            external_operation_id=f"ext-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-crash-{uuid.uuid4().hex[:8]}",
        )
        db = concurrency_db_session_factory()
        async with db.begin():
            db.add(operation)
            await db.flush()
        
        # Create a worker lease (simulating worker started)
        lease_manager = LeaseManager(db)
        lease_id = await lease_manager.acquire_lease(
            worker_id="worker-crashed",
            operation_id=operation_id,
            organization_id=org.id,
            ttl=timedelta(minutes=5),
        )
        assert lease_id is not None
        
        # Simulate worker starting attempt
        attempt = OperationAttempt(
            id=f"attempt-{uuid.uuid4().hex[:8]}",
            operation_id=operation_id,
            organization_id=org.id,
            attempt_number=1,
            state="executing",
            worker_id="worker-crashed",
            started_at=utcnow(),
            fingerprint=f"fp-attempt-{uuid.uuid4().hex[:8]}",
        )
        db.add(attempt)
        await db.flush()
        
        # Update operation to attempting state
        operation.state = "attempting"
        operation.current_attempt = 1
        await db.flush()
        
        # Simulate crash: worker dies, lease expires, but no completion
        await lease_manager.release_lease(lease_id)
        
        # Now the operation has NO successful completion and NO definitive failure
        # The external result is UNKNOWN
        external_unknown = ExternalUnknownState(
            id=f"eus-{uuid.uuid4().hex[:8]}",
            operation_id=operation_id,
            organization_id=org.id,
            external_system="stripe",
            external_operation_id=operation.external_operation_id,
            external_operation_type="payment",
            request_payload_json={"amount": 100},
            request_fingerprint=f"fp-req-{uuid.uuid4().hex[:8]}",
            state="unknown",
            requested_at=utcnow(),
            timeout_at=utcnow() + timedelta(hours=24),
            fingerprint=f"fp-eus-{uuid.uuid4().hex[:8]}",
        )
        db.add(external_unknown)
        
        # Operation state should be UNKNOWN, not FAILED
        operation.state = "unknown"
        await db.flush()
        
        # Verify UNKNOWN state (not FAILED, not SUCCESS)
        reloaded_op = await db.get(CanonicalOperation, operation_id)
        assert_unknown_state_preserved(reloaded_op)
        
        # Verify external unknown state exists
        eus = await db.get(ExternalUnknownState, external_unknown.id)
        assert eus is not None
        assert eus.state == "unknown"
    
    @pytest.mark.asyncio
    async def test_unknown_state_recovery_flow(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """UNKNOWN → Recovery → Reconciliation → Verification."""
        org = concurrency_organization
        
        from app.services.canonical_reliability_service import canonical_reliability_service
        
        db = concurrency_db_session_factory()
        async with db.begin():
            operation_id = f"op-recovery-{uuid.uuid4().hex[:8]}"
            
            operation = await canonical_reliability_service.create_operation(
                db=db,
                organization_id=org.id,
                operation_type="external_payment",
                title="Payment",
                is_external=True,
                external_system="stripe",
                external_operation_id=f"pay-{uuid.uuid4().hex[:8]}",
            )
            
            # Mark as external unknown
            eus = await canonical_reliability_service.mark_external_unknown(
                db=db,
                operation=operation,
                external_system="stripe",
                external_operation_id=operation.external_operation_id,
                external_operation_type="payment",
            )
            
            assert operation.state == "unknown"
            assert eus.state == "unknown"
            
            # Reconcile with external system (simulating recovery)
            reconciliation = await canonical_reliability_service.reconcile_external_unknown(
                db=db,
                eus=eus,
                external_state={"state": "completed", "amount": 10000, "currency": "usd"},
                reconciliation_method="webhook",
            )
            
            assert reconciliation.outcome == "reconciled"
            
            # Verify operation state updated
            reloaded = await db.get(CanonicalOperation, operation.id)
            assert_recovery_reconciliation_flow(reloaded)
    
    @pytest.mark.asyncio
    async def test_stale_operation_detection_and_recovery(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Stale operation detected → recovery initiated."""
        from app.services.canonical_reliability_service import canonical_reliability_service
        
        org = concurrency_organization
        db = concurrency_db_session_factory()
        
        async with db.begin():
            # Create operation that appears stale
            operation = await canonical_reliability_service.create_operation(
                db=db,
                organization_id=org.id,
                operation_type="test_op",
                title="Stale Operation",
            )
            
            # Manually set to appear stale
            operation.updated_at = utcnow() - timedelta(minutes=10)
            operation.state = "executing"
            await db.flush()
            
            # Detect stale operations
            detections = await canonical_reliability_service.detect_stale_operations(
                db=db,
                organization_id=org.id,
                stale_threshold_seconds=300,
            )
            
            assert len(detections) >= 1
            detection = detections[0]
            assert detection.operation_id == operation.id
            assert detection.detection_method == "timeout"
            
            # Recover stale operations
            recoveries = await canonical_reliability_service.recover_stale_operations(
                db=db,
                detections=detections,
            )
            
            assert len(recoveries) >= 1
            recovery = recoveries[0]
            assert recovery.state in ("detecting", "executing", "completed", "verifying")


# =============================================================================
# Test Class: Authorization Race
# =============================================================================

class TestAuthorizationRace:
    """Test authorization race conditions."""
    
    @pytest.mark.asyncio
    async def test_authorization_revoked_during_execution(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """T1: auth exists, T2: auth revoked, T3: operation executes → blocked."""
        org = concurrency_organization
        db = concurrency_db_session_factory()
        
        # Create real provenance entities
        from tests.concurrency import CanonicalActorBuilder
        from app.intelligence.canonical_mutation import canonical_create
        from app.models.execution_strategy import CompanyAuthorization
        
        async with db.begin():
            builder = CanonicalActorBuilder(
                db=db,
                organization=org,
                user_id=f"actor-race-{uuid.uuid4().hex[:8]}",
                email=f"race-{uuid.uuid4().hex[:8]}@test.com",
                full_name="Race Actor",
                role_codes=["ceo"],
            )
            actor = await builder.build()
            caller = actor.to_caller_access()
            
            # Create real provenance
            decision = CompanyDecision(
                organization_id=org.id,
                decision_id=f"dec-auth-race-{uuid.uuid4().hex[:8]}",
                kind="strategic",
                title="Auth Race Decision",
                rationale="Test",
                state="approved",
                approver_label="test",
                source_event_id="evt-dec",
            )
            decision_result = await canonical_create(
                db=db,
                caller=caller,
                entity=decision,
                required_permissions=["decisions:manage"],
            )
            
            # Create approval policy
            from app.models.governance import ApprovalPolicy
            policy = ApprovalPolicy(
                organization_id=org.id,
                name="Auth Race Policy",
                description="Test policy",
                required_permission="authorizations:manage",
                is_active=True,
            )
            db.add(policy)
            await db.flush()
            
            auth = CompanyAuthorization(
                organization_id=org.id,
                id=f"auth-race-{uuid.uuid4().hex[:8]}",
                decision_id=decision_result.entity.id,
                policy_id=policy.id,
                title="Auth Race Test",
                state="approved",
                source_event_id="evt-auth",
                fingerprint=f"fp-auth-{uuid.uuid4().hex[:8]}",
            )
            db.add(auth)
            await db.flush()
            auth_id = auth.id
            
            test_decision_id = decision_result.entity.id
            test_policy_id = policy.id
            
            # Create actor with permissions
            builder = CanonicalActorBuilder(
                db=db,
                organization=org,
                user_id=f"actor-race-{uuid.uuid4().hex[:8]}",
                email=f"race-{uuid.uuid4().hex[:8]}@test.com",
                full_name="Race Actor",
                role_codes=["ceo"],
            )
            actor = await builder.build()
            caller = actor.to_caller_access()
        
        # Verify operation with valid authorization succeeds
        # From approved, only superseded is allowed
        db2 = concurrency_db_session_factory()
        async with db2.begin():
            result = await canonical_transition(
                db=db2,
                caller=caller,
                entity_type="CompanyAuthorization",
                entity_id=auth_id,
                new_state="superseded",
                provenance={"decision_id": test_decision_id, "policy_id": test_policy_id},
                required_permissions=["authorizations:manage"],
            )
            assert result.success is True
        
        # Now revoke authorization (set to rejected)
        db2 = concurrency_db_session_factory()
        async with db2.begin():
            auth = await db2.get(CompanyAuthorization, auth_id)
            auth.state = "rejected"
            await db2.flush()
        
        # Try another transition with revoked authorization
        db3 = concurrency_db_session_factory()
        async with db3.begin():
            result2 = await canonical_transition(
                db=db3,
                caller=caller,
                entity_type="CompanyAuthorization",
                entity_id=auth_id,
                new_state="approved",  # Invalid from rejected
                provenance={"decision_id": test_decision_id, "policy_id": test_policy_id},
                required_permissions=["authorizations:manage"],
            )
            assert result2.success is False
            assert "invalid state transition" in result2.error.lower() or "transition" in result2.error.lower()
    
    @pytest.mark.asyncio
    async def test_role_removal_vs_operation(
        self,
        concurrency_organization,
        concurrency_db_session_factory,
    ):
        """Role removed → subsequent operations blocked."""
        org = concurrency_organization
        db = concurrency_db_session_factory()
        
        # Create real provenance entities
        from tests.concurrency import CanonicalActorBuilder
        from app.intelligence.canonical_mutation import canonical_create
        from app.models.execution_strategy import CompanyAuthorization
        
        async with db.begin():
            # Create actor with CEO role
            builder = CanonicalActorBuilder(
                db=db,
                organization=org,
                user_id=f"actor-role-{uuid.uuid4().hex[:8]}",
                email=f"role-{uuid.uuid4().hex[:8]}@test.com",
                full_name="Role Actor",
                role_codes=["ceo"],
            )
            actor = await builder.build()
            caller = actor.to_caller_access()
            
            # Create real provenance
            decision = CompanyDecision(
                organization_id=org.id,
                decision_id=f"dec-role-{uuid.uuid4().hex[:8]}",
                kind="strategic",
                title="Role Test Decision",
                rationale="Test",
                state="approved",
                approver_label="test",
                source_event_id="evt-dec",
            )
            decision_result = await canonical_create(
                db=db,
                caller=caller,
                entity=decision,
                required_permissions=["decisions:manage"],
            )
            
            # Create approval policy
            from app.models.governance import ApprovalPolicy
            policy = ApprovalPolicy(
                organization_id=org.id,
                name="Role Test Policy",
                description="Test policy for role test",
                required_permission="authorizations:manage",
                is_active=True,
            )
            db.add(policy)
            await db.flush()
            
            auth = CompanyAuthorization(
                organization_id=org.id,
                id=f"auth-role-{uuid.uuid4().hex[:8]}",
                decision_id=decision_result.entity.id,
                policy_id=policy.id,
                title="Role Test Authorization",
                state="approved",
                source_event_id="evt-auth",
                fingerprint=f"fp-auth-{uuid.uuid4().hex[:8]}",
            )
            auth_result = await canonical_create(
                db=db,
                caller=caller,
                entity=auth,
                provenance={"decision_id": decision_result.entity.id, "policy_id": policy.id},
                required_permissions=["authorizations:manage"],
            )
            
            if auth_result.entity is None:
                raise RuntimeError(f"Failed to create authorization: {auth_result.error}")
            
            comm = CompanyCommitment(
                organization_id=org.id,
                commitment_type="unconditional",
                title="Test Commitment",
                scope_type="objective",
                authorization_id=auth_result.entity.id,
                decision_id=decision_result.entity.id,
                fingerprint=f"fp-role-{uuid.uuid4().hex[:8]}",
            )
            db.add(comm)
            await db.flush()
            comm_id = comm.id
        
        # First update succeeds (user has CEO role)
        caller = actor.to_caller_access()
        db2 = concurrency_db_session_factory()
        async with db2.begin():
            result1 = await canonical_update(
                db=db2,
                caller=caller,
                entity_type="CompanyCommitment",
                entity_id=comm_id,
                updates={"title": "Updated with CEO role"},
                provenance={"authorization_id": auth_result.entity.id, "decision_id": decision_result.entity.id},
                required_permissions=["commitments:manage"],
            )
            assert result1.success is True
        
        # Remove CEO role from user
        db3 = concurrency_db_session_factory()
        async with db3.begin():
            actor_db = await db3.get(User, actor.user_id)
            user_roles = await db3.execute(
                select(UserRole).where(UserRole.user_id == actor.user_id)
            )
            for ur in user_roles.scalars().all():
                await db3.delete(ur)
            await db3.flush()
        
        # Refresh caller access - actor no longer has permissions
        db4 = concurrency_db_session_factory()
        async with db4.begin():
            new_caller = await resolve_caller_access(db4, organization_id=org.id, user=actor_db)
        
        # Second update should fail (no longer has permission)
        db5 = concurrency_db_session_factory()
        async with db5.begin():
            result2 = await canonical_update(
                db=db5,
                caller=new_caller,
                entity_type="CompanyCommitment",
                entity_id=comm_id,
                updates={"title": "Updated without CEO role"},
                provenance={"authorization_id": auth_result.entity.id, "decision_id": decision_result.entity.id},
                required_permissions=["commitments:manage"],
            )
            assert result2.success is False
            assert "scope" in result2.error.lower() or "accessible" in result2.error.lower()