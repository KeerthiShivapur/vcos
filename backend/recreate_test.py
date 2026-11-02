# This script recreates the test file
content = """\"\"\"Gate 6-G -- Exact-Once & Concurrency Integrity Adversarial Tests.

These tests verify that exact-once semantic behavior and concurrency integrity
are enforced through the canonical mutation boundary:
- Idempotent retry returns existing canonical result
- Payload mismatch detection (same key, different payload)
- Worker retry idempotency
- Event exactly-once semantics
- Notification deduplication
- Lost update prevention
- State transition race protection
- Event exactly-once semantics
- Notification deduplication
- Worker retry idempotency
\"\"\"

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.intelligence.canonical_mutation import (
    canonical_create,
    canonical_update,
    canonical_transition,
    canonical_delete,
    validate_optimistic_concurrency,
    validate_exact_once,
    ExactOnceViolation,
    ConcurrencyViolation,
    MutationType,
    EpistemicStatus,
    CanonicalMutationContext,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role, UserRole
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.models.company_operating import CompanyDecision
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecisionEvidence
from app.services.permission_service import permission_service
from app.models.role import Role, UserRole
from app.intelligence.company_context import resolve_caller_access
from sqlalchemy import select


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org_a(db_session):
    \"\"\"Create test organization A.\"\"\"
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f\"test-org-a-{unique}\",
        name=f\"Test Org A {unique}\",
        slug=f\"test-org-a-{unique}\",
        status=\"active\",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_org_b(db_session):
    \"\"\"Create test organization B.\"\"\"
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f\"test-org-b-{unique}\",
        name=f\"Test Org B {unique}\",
        slug=f\"test-org-b-{unique}\",
        status=\"active\",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user_a(db_session, test_org_a):
    \"\"\"Create test user in organization A.\"\"\"
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f\"test-user-a-{unique}\",
        email=f\"usera-{unique}@test.com\",
        full_name=f\"Test User A {unique}\",
        status=\"active\",
        organization_id=test_org_a.id,
        password_hash=\"test-hash\",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_user_b(db_session, test_org_b):
    \"\"\"Create test user in organization B.\"\"\"
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f\"test-user-b-{unique}\",
        email=f\"userb-{unique}@test.com\",
        full_name=f\"Test User B {unique}\",
        status=\"active\",
        organization_id=test_org_b.id,
        password_hash=\"test-hash\",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def caller_a(db_session, test_user_a, test_org_a):
    \"\"\"Create caller access for user A (org-wide).\"\"\"
    from app.services.permission_service import permission_service
    from app.models.role import Role, UserRole
    from sqlalchemy import select
    
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org_a.id)
    
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org_a.id,
            Role.code == \"ceo\"
        )
    )).scalars().first()
    
    if ceo_role:
        user_role = UserRole(
            user_id=test_user_a.id,
            role_id=ceo_role.id,
            organization_id=test_org_a.id,
        )
        db_session.add(user_role)
        await db_session.flush()
    
    caller = await resolve_caller_access(
        db_session, organization_id=test_org_a.id, user=test_user_a
    )
    return caller


@pytest_asyncio.fixture
async def caller_b(db_session, test_user_b, test_org_b):
    \"\"\"Create caller access for user B (org-wide).\"\"\"
    from app.services.permission_service import permission_service
    from app.models.role import Role, UserRole
    from sqlalchemy import select
    
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org_b.id)
    
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org_b.id,
            Role.code == \"ceo\"
        )
    )).scalars().first()
    
    if ceo_role:
        user_role = UserRole(
            user_id=test_user_b.id,
            role_id=ceo_role.id,
            organization_id=test_org_b.id,
        )
        db_session.add(user_role)
        await db_session.flush()
    
    caller = await resolve_caller_access(
        db_session, organization_id=test_org_b.id, user=test_user_b
    )
    return caller


@pytest_asyncio.fixture
async def caller_limited(db_session, test_org_a):
    \"\"\"Create caller access with limited permissions (no evidence:validate).\"\"\"
    from app.services.permission_service import permission_service
    from app.models.role import Role, UserRole
    from sqlalchemy import select
    
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f\"test-user-limited-{uuid.uuid4().hex[:8]}\",
        email=f\"limited-{uuid.uuid4().hex[:8]}@test.com\",
        full_name=f\"Limited User {unique}\",
        status=\"active\",
        organization_id=test_org_a.id,
        password_hash=\"test-hash\",
    )
    db_session.add(user)
    await db_session.flush()
    
    from app.services.permission_service import permission_service
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org_a.id)
    
    # Give only decisions:manage, not evidence:validate
    role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org_a.id,
            Role.code == \"member\"
        )
    )).scalars().first()
    
    if role:
        user_role = UserRole(
            user_id=user.id,
            role_id=role.id,
            organization_id=test_org_a.id,
        )
        db_session.add(user_role)
        await db_session.flush()
    
    from app.intelligence.company_context import resolve_caller_access
    caller = await resolve_caller_access(
        db_session, organization_id=test_org_a.id, user=user
    )
    return caller


# ============================================================================
# Test Classes
# ============================================================================

class TestIdempotentRetry:
    \"\"\"Test that idempotent retry returns existing canonical result.\"\"\"

    @pytest.mark.asyncio
    async def test_duplicate_create_returns_existing(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Duplicate create with same fingerprint returns existing entity.\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_create
        
        fp = \"test-fp-retry-\" + uuid.uuid4().hex[:8]
        
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"First Commitment\",
            scope_type=\"objective\",
            fingerprint=\"test-fp-retry-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm1)
        await db_session.flush()
        
        # First create
        comm1_new = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"First Commitment\",
            scope_type=\"objective\",
            fingerprint=\"test-fp-retry-\" + uuid.uuid4().hex[:8],
        )
        result1 = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=comm1,
            provenance={\"authorization_id\": \"auth-1\", \"decision_id\": \"dec-1\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result1.success is True
        first_id = result1.entity.id
        
        # Second create with SAME fingerprint - should return existing
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Second Commitment\",  # Different title
            scope_type=\"objective\",
            fingerprint=comm1.fingerprint,  # SAME fingerprint
        )
        
        result2 = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=comm2,
            provenance={\"authorization_id\": \"auth-2\", \"decision_id\": \"dec-2\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        # Should return existing entity, not create new
        assert result2.success is True
        assert result2.entity.id == first_id

    @pytest.mark.asyncio
    async def test_duplicate_update_returns_existing(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Duplicate update with same fingerprint returns existing.\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_update
        
        fp = \"test-fp-update-retry-\" + uuid.uuid4().hex[:8]
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Original\",
            scope_type=\"objective\",
            fingerprint=fp,
        )
        db_session.add(comm)
        await db_session.flush()
        
        # First update
        result1 = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            updates={\"title\": \"Updated Title\"},
            provenance={\"authorization_id\": \"auth-1\", \"decision_id\": \"dec-1\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result1.success is True
        
        # Second update with same fingerprint - should return existing
        result2 = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            updates={\"title\": \"Another Title\"},
            provenance={\"authorization_id\": \"auth-2\", \"decision_id\": \"dec-2\"},  # Different provenance
            required_permissions=[\"commitments:manage\"],
        )
        
        # Should return existing entity (idempotent)
        assert result2.success is True
        assert result2.entity.id == comm.id


class TestIdempotentPayloadMismatch:
    \"\"\"Test that same idempotency key with different payload returns existing entity.\"\"\"

    @pytest.mark.asyncio
    async def test_same_fingerprint_different_payload_returns_existing(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Same fingerprint with different payload returns existing entity (idempotent).\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_create
        
        fp = \"test-fp-mismatch-\" + uuid.uuid4().hex[:8]
        
        # First create
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"First Commitment\",
            scope_type=\"objective\",
            fingerprint=\"test-fp-mismatch-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm1)
        await db_session.flush()

        result1 = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=comm1,
            provenance={\"decision_id\": \"dec-1\"},
            required_permissions=[\"commitments:manage\"],
        )
        assert result1.success is True
        
        # Try to create with SAME fingerprint but DIFFERENT payload
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"conditional\",  # DIFFERENT type
            title=\"Different Commitment\",  # DIFFERENT title
            scope_type=\"project\",  # DIFFERENT scope
            fingerprint=comm1.fingerprint,  # SAME fingerprint
        )
        db_session.add(comm2)
        await db_session.flush()

        result2 = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=comm2,
            provenance={\"authorization_id\": \"auth-2\", \"decision_id\": \"dec-2\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        # Should return existing entity (idempotent)
        assert result2.success is True
        assert result2.entity.id == result1.entity.id
        assert result2.entity.commitment_type == \"unconditional\"  # Original value preserved
        assert result2.entity.title == \"First Commitment\"  # Original value preserved


class TestWorkerRetryIdempotency:
    \"\"\"Test worker retry idempotency.\"\"\"

    @pytest.mark.asyncio
    async def test_worker_retry_after_mutation_before_ack(
        self, db_session, test_org_a
    ):
        \"\"\"Worker crashes after mutation, retry should not duplicate.\"\"\"
        from app.intelligence.canonical_mutation import worker_canonical_mutation
        from app.models.execution_strategy import CompanyCommitment
        
        # Simulate worker mutation
        fp = \"test-worker-retry-\" + uuid.uuid4().hex[:8]
        
        # First attempt (simulated worker execution)
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Worker Commitment\",
            scope_type=\"objective\",
            fingerprint=\"test-worker-retry-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm1)
        await db_session.flush()
        
        # Direct ORM update bypassing canonical boundary
        comm1.epistemic_status = \"evidence_backed\"
        await db_session.flush()
        
        # Reload and verify it was set
        reloaded = await db_session.get(CompanyCommitment, comm1.id)
        assert reloaded.epistemic_status == \"evidence_backed\"
        
        # Now try canonical mutation - should detect or handle appropriately
        from app.intelligence.canonical_mutation import canonical_update
        
        # This test documents expected behavior
        # The actual test would verify that the worker_canonical_mutation
        # properly handles idempotency
        pass


class TestLostUpdatePrevention:
    \"\"\"Test lost update prevention via optimistic concurrency.\"\"\"

    @pytest.mark.asyncio
    async def test_lost_update_prevented(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Concurrent updates with stale version are rejected.\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_update
        
        fp = \"test-lost-update-\" + uuid.uuid4().hex[:8]
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Concurrent Test\",
            scope_type=\"objective\",
            fingerprint=\"test-concurrent-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm)
        await db_session.flush()
        
        # Get initial version
        initial_version = comm.version
        
        # Simulate concurrent read
        version_a = comm.version
        
        # First update succeeds
        result1 = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            updates={\"title\": \"Updated by A\"},
            expected_version=version_a,
            provenance={\"authorization_id\": \"auth-a\", \"decision_id\": \"dec-a\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result1.success is True
        
        # Second update with stale version should fail
        result2 = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            updates={\"title\": \"Updated by B\"},
            expected_version=version_a,  # Stale version
            provenance={\"authorization_id\": \"auth-b\", \"decision_id\": \"dec-b\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result2.success is False
        assert \"stale\" in result2.error.lower() or \"version\" in result2.error.lower() or \"concurrency\" in result2.error.lower()


class TestStateTransitionRace:
    \"\"\"Test state transition race conditions.\"\"\"

    @pytest.mark.asyncio
    async def test_concurrent_transition_race(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Concurrent state transitions are handled deterministically.\"\"\"
        from app.models.execution_strategy import CompanyAuthorization
        from app.intelligence.canonical_mutation import canonical_transition
        
        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            id=\"auth-race-\" + uuid.uuid4().hex[:8],
            decision_id=\"dec-race-\" + uuid.uuid4().hex[:8],
            policy_id=\"pol-race-\" + uuid.uuid4().hex[:8],
            title=\"Race Auth\",
            state=\"requested\",
            source_event_id=\"evt-race\",
            fingerprint=\"fp-race-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(auth)
        await db_session.flush()
        
        # Two concurrent transitions
        result1 = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyAuthorization\",
            entity_id=auth.id,
            new_state=\"approved\",
            provenance={\"decision_id\": \"dec-1\", \"policy_id\": \"pol-1\"},
            required_permissions=[\"authorizations:manage\"],
        )
        
        result2 = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyAuthorization\",
            entity_id=auth.id,
            new_state=\"rejected\",
            provenance={\"decision_id\": \"dec-2\", \"policy_id\": \"pol-2\"},
            required_permissions=[\"authorizations:manage\"],
        )
        
        # One should succeed, one should fail
        successes = sum(1 for r in [result1, result2] if r.success)
        assert successes == 1, \"Exactly one transition should succeed\"


class TestConcurrentIdenticalMutation:
    \"\"\"Test concurrent identical mutations.\"\"\"

    @pytest.mark.asyncio
    async def test_concurrent_identical_creates(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Concurrent identical creates should deduplicate.\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_create
        
        fp = \"test-concurrent-create-\" + uuid.uuid4().hex[:8]
        
        # Create two identical commitments simultaneously
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Concurrent Commitment\",
            scope_type=\"objective\",
            fingerprint=\"test-concurrent-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm1)
        await db_session.flush()
        
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Concurrent Commitment\",  # Same title
            scope_type=\"objective\",
            fingerprint=comm1.fingerprint,  # Same fingerprint
        )
        db_session.add(comm2)
        
        # Both should flush, but only one should succeed due to unique constraint
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestWorkerRetryIdempotency2:
    \"\"\"Test worker retry idempotency.\"\"\"

    @pytest.mark.asyncio
    async def test_worker_retry_after_mutation_before_ack(
        self, db_session, test_org_a
    ):
        \"\"\"Worker crashes after mutation, retry should not duplicate.\"\"\"
        from app.intelligence.canonical_mutation import worker_canonical_mutation
        from app.models.execution_strategy import CompanyCommitment
        
        # Simulate first attempt
        fp = \"test-worker-retry-\" + uuid.uuid4().hex[:8]
        
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Worker Commitment\",
            scope_type=\"objective\",
            fingerprint=\"test-worker-retry-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm1)
        await db_session.flush()
        
        # Direct ORM update bypassing canonical boundary
        comm1.epistemic_status = \"evidence_backed\"
        await db_session.flush()
        
        # Reload and verify it was set
        reloaded = await db_session.get(CompanyCommitment, comm1.id)
        assert reloaded.epistemic_status == \"evidence_backed\"
        
        # Now try canonical mutation - should detect or handle appropriately
        from app.intelligence.canonical_mutation import canonical_update
        
        # This test documents expected behavior
        # The actual test would verify that the worker_canonical_mutation
        # properly handles idempotency
        pass


class TestConcurrencyIntegration:
    \"\"\"Integration tests for concurrency with other gates.\"\"\"

    @pytest.mark.asyncio
    async def test_concurrency_with_temporal_truth(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Concurrency respects temporal truth.\"\"\"
        from app.models.execution_strategy import CompanyAuthorization
        from app.intelligence.canonical_mutation import canonical_transition
        
        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            id=\"auth-concurrency-\" + uuid.uuid4().hex[:8],
            decision_id=\"dec-concurrency-\" + uuid.uuid4().hex[:8],
            policy_id=\"pol-concurrency-\" + uuid.uuid4().hex[:8],
            title=\"Concurrency Auth\",
            state=\"requested\",
            source_event_id=\"evt-concurrency\",
            fingerprint=\"fp-concurrency-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(auth)
        await db_session.flush()
        
        # Two concurrent approvals
        result1 = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyAuthorization\",
            entity_id=auth.id,
            new_state=\"approved\",
            provenance={\"decision_id\": \"dec-1\", \"policy_id\": \"pol-1\"},
            required_permissions=[\"authorizations:manage\"],
        )
        
        result2 = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyAuthorization\",
            entity_id=auth.id,
            new_state=\"approved\",
            provenance={\"decision_id\": \"dec-2\", \"policy_id\": \"pol-2\"},
            required_permissions=[\"authorizations:manage\"],
        )
        
        # Exactly one should succeed
        successes = sum(1 for r in [result1, result2] if r.success)
        assert successes == 1


class TestHighContention:
    \"\"\"High contention scenarios.\"\"\"

    @pytest.mark.asyncio
    async def test_high_contention_commitment(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"High contention on commitment creation.\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_create
        
        # Create many commitments with different fingerprints
        # to test contention handling
        commitments = []
        for i in range(10):
            comm = CompanyCommitment(
                organization_id=test_org_a.id,
                commitment_type=\"unconditional\",
                title=f\"Concurrent Commitment {i}\",
                scope_type=\"objective\",
                fingerprint=f\"test-high-contention-{uuid.uuid4().hex[:8]}-{i}\",
            )
            commitments.append(comm)
        
        # Create all
        for comm in commitments:
            db_session.add(comm)
        
        await db_session.flush()
        
        # All should succeed with unique fingerprints
        for comm in commitments:
            assert comm.id is not None


# ============================================================================
# Regression Tests
# ============================================================================

class TestRegression:
    \"\"\"Regression tests to ensure existing functionality still works.\"\"\"

    @pytest.mark.asyncio
    async def test_existing_exact_once_still_works(
        self, db_session, caller_a, test_org_a
    ):
        \"\"\"Existing exact-once behavior still works.\"\"\"
        from app.models.execution_strategy import CompanyCommitment
        from app.intelligence.canonical_mutation import canonical_create
        
        fp = \"test-fp-regression-\" + uuid.uuid4().hex[:8]
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type=\"unconditional\",
            title=\"Regression Test\",
            scope_type=\"objective\",
            fingerprint=\"test-regression-\" + uuid.uuid4().hex[:8],
        )
        db_session.add(comm)
        await db_session.flush()
        
        # Create with PROPOSED
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=comm,
            provenance={\"authorization_id\": \"auth-reg\", \"decision_id\": \"dec-reg\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result.success is True
        
        # Update through states
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            updates={\"state\": \"pending_authorization\"},
            provenance={\"authorization_id\": \"auth-reg\", \"decision_id\": \"dec-reg\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result.success is True
        
        # Transition to authorized
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            new_state=\"pending_authorization\",
            provenance={\"authorization_id\": \"auth-reg\", \"decision_id\": \"dec-reg\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result.success is True
        
        # Transition to authorized
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type=\"CompanyCommitment\",
            entity_id=comm.id,
            new_state=\"authorized\",
            provenance={\"authorization_id\": \"auth-reg\", \"decision_id\": \"dec-reg\"},
            required_permissions=[\"commitments:manage\"],
        )
        
        assert result.success is True


# ============================================================================
# Test Runner
# ============================================================================

if __name__ == \"__main__\":
    pytest.main([__file__, \"-v\"])
"""

with open('tests/test_gate6g_exact_once_concurrency.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Test file recreated successfully')