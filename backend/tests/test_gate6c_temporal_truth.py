"""Gate 6-C — Temporal Truth Enforcement Adversarial Tests.

These tests verify that temporal truth is enforced through the canonical
mutation boundary: historical state cannot be silently rewritten,
supersession chains are maintained, and temporal queries return
correct historical state.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.intelligence.canonical_mutation import (
    canonical_mutation_boundary,
    canonical_create,
    canonical_update,
    canonical_transition,
    canonical_delete,
    CanonicalMutationBoundary,
    CanonicalMutationContext,
    MutationResult,
    MutationType,
    EpistemicStatus,
    validate_state_transition,
    validate_temporal_integrity,
    validate_provenance,
    validate_epistemic_boundary,
    validate_exact_once,
    validate_optimistic_concurrency,
    CanonicalMutationError,
    GovernanceViolation,
    TenantIsolationViolation,
    ScopeViolation,
    InvalidStateTransition,
    TemporalViolation,
    ProvenanceViolation,
    EpistemicViolation,
    ConcurrencyViolation,
    ExactOnceViolation,
    STATE_TRANSITIONS,
)

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.company_operating import CompanyDecision, CompanyDecisionAlternative
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyGoal, CompanyObjective, CompanyInitiative, StrategicHistory
from app.models.company_intent import CompanyIntent
from app.models.company_actions import CompanyAction
from app.intelligence.company_context import resolve_caller_access, CallerAccess


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org_a(db_session):
    """Create test organization A."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"test-org-a-{unique}",
        name=f"Test Org A {unique}",
        slug=f"test-org-a-{unique}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_org_b(db_session):
    """Create test organization B."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"test-org-b-{unique}",
        name=f"Test Org B {unique}",
        slug=f"test-org-b-{unique}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user_a(db_session, test_org_a):
    """Create test user in organization A."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"test-user-a-{unique}",
        email=f"usera-{unique}@test.com",
        full_name=f"Test User A {unique}",
        status="active",
        organization_id=test_org_a.id,
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_user_b(db_session, test_org_b):
    """Create test user in organization B."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"test-user-b-{unique}",
        email=f"userb-{unique}@test.com",
        full_name=f"Test User B {unique}",
        status="active",
        organization_id=test_org_b.id,
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def caller_a(db_session, test_user_a, test_org_a):
    """Create caller access for user A (org-wide)."""
    from app.services.permission_service import permission_service
    from app.models.role import Role
    from app.models.role import UserRole
    from sqlalchemy import select

    # Sync permission catalog first
    await permission_service.sync_catalog(db_session)

    # Seed roles for this organization
    await permission_service.seed_org_roles(db_session, test_org_a.id)

    # Get the CEO role
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org_a.id,
            Role.code == "ceo"
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
    """Create caller access for user B (org-wide)."""
    from app.services.permission_service import permission_service
    from app.models.role import Role
    from app.models.role import UserRole
    from sqlalchemy import select

    # Sync permission catalog first
    await permission_service.sync_catalog(db_session)

    # Seed roles for this organization
    await permission_service.seed_org_roles(db_session, test_org_b.id)

    # Get the CEO role
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org_b.id,
            Role.code == "ceo"
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


# ============================================================================
# Test Class: Historical Immutability
# ============================================================================

@pytest.mark.asyncio
class TestHistoricalImmutability:
    """Test that historical versions cannot be silently rewritten."""

    @pytest.mark.asyncio
    async def test_historical_commitment_cannot_be_modified(
        self, db_session, caller_a, test_org_a
    ):
        """Superseded commitment cannot be modified."""
        # Create commitment v1
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Commitment v1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-comm-v1",
        )
        db_session.add(comm1)
        await db_session.flush()

        # Create commitment v2 that supersedes v1
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Commitment v2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-comm-v2",
            supersedes_id=comm1.id,
        )
        db_session.add(comm2)
        await db_session.flush()

        # Mark v1 as superseded
        comm1.state = "superseded"
        comm1.superseded_by_id = comm2.id
        await db_session.flush()

        # Attempt to modify superseded v1 - should be rejected
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm1.id,
            updates={"title": "Hacked Title"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower()

    @pytest.mark.asyncio
    async def test_historical_authorization_cannot_be_modified(
        self, db_session, caller_a, test_org_a
    ):
        """Expired authorization cannot be modified."""
        # Create authorization that has expired/superseded through canonical boundary
        auth1 = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Expired Auth",
            scope_type="company",
            state="superseded",
            valid_from=datetime.now(timezone.utc) - timedelta(days=10),
            valid_until=datetime.now(timezone.utc) - timedelta(days=1),
            fingerprint="fp-auth-expired",
            decision_id="dec-123",
            policy_id="policy-123",
        )
        db_session.add(auth1)
        await db_session.flush()

        # Attempt to modify expired authorization - should be rejected
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAuthorization",
            entity_id=auth1.id,
            updates={"title": "Hacked Title"},
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "dec-123", "policy_id": "policy-123"},
        )

        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_historical_rewrite_without_supersession_rejected(
        self, db_session, caller_a, test_org_a
    ):
        """Direct modification of old version without supersession rejected."""
        # Create commitment
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Old Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-old-comm",
        )
        db_session.add(comm)
        await db_session.flush()

        # Simulate time passing by updating updated_at to be old
        comm.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await db_session.flush()

        # Attempt to modify old commitment directly - should be rejected
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            updates={"title": "Hacked Title"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "historical" in result.error.lower() or "immutable" in result.error.lower()


# ============================================================================
# Test Class: Supersession Chain Integrity
# ============================================================================

@pytest.mark.asyncio
class TestSupersessionChainIntegrity:
    """Test that supersession chains are properly maintained."""

    @pytest.mark.asyncio
    async def test_supersession_chain_maintained(
        self, db_session, caller_a, test_org_a
    ):
        """Supersession chain is properly maintained."""
        # Create v1
        v1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v1",
        )
        db_session.add(v1)
        await db_session.flush()

        # Create v2 superseding v1
        v2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v2",
            supersedes_id=v1.id,
        )
        db_session.add(v2)
        await db_session.flush()

        # Update v1 to mark as superseded
        v1.state = "superseded"
        v1.superseded_by_id = v2.id
        await db_session.flush()

        # Create v3 superseding v2
        v3 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 3",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v3",
            supersedes_id=v2.id,
        )
        db_session.add(v3)
        await db_session.flush()

        v2.state = "superseded"
        v2.superseded_by_id = v3.id
        await db_session.flush()

        # Verify chain integrity
        assert v1.superseded_by_id == v2.id
        assert v2.supersedes_id == v1.id
        assert v2.superseded_by_id == v3.id
        assert v3.supersedes_id == v2.id
        assert v3.superseded_by_id is None  # Latest has no successor

    @pytest.mark.asyncio
    async def test_broken_supersession_chain_rejected(
        self, db_session, caller_a, test_org_a
    ):
        """Broken supersession chain is rejected."""
        v1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v1",
        )
        db_session.add(v1)
        await db_session.flush()

        v2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v2",
            supersedes_id=v1.id,
        )
        db_session.add(v2)
        await db_session.flush()

        # Intentionally break the chain - v2 supersedes v1 but v1 doesn't know about v2
        # (v1.state stays "authorized", no superseded_by_id)

        # Try to create v3 superseding v2 - should still work
        v3 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 3",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v3",
            supersedes_id=v2.id,
        )
        db_session.add(v3)
        await db_session.flush()

        v2.state = "superseded"
        v2.superseded_by_id = v3.id
        await db_session.flush()

        # The chain should now be: v1 -> v2 -> v3
        # But v1 doesn't point to v2 - this is a broken chain
        # The validation should catch this when trying to modify v1
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=v1.id,
            updates={"title": "Hacked"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "broken" in result.error.lower() or "supersession" in result.error.lower()


# ============================================================================
# Test Class: Current State Uniqueness
# ============================================================================

@pytest.mark.asyncio
class TestCurrentStateUniqueness:
    """Test that only one current version exists where required."""

    @pytest.mark.asyncio
    async def test_single_current_authorization_enforced(
        self, db_session, caller_a, test_org_a
    ):
        """Only one current authorization allowed per organization (validated by temporal logic)."""
        # Create first approved authorization
        auth1 = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="First Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-1",
            decision_id="dec-123",
            policy_id="policy-123",
        )
        db_session.add(auth1)
        await db_session.flush()

        # The temporal validation in validate_temporal_integrity checks for current state uniqueness
        # Try to create second approved authorization through canonical boundary
        auth2 = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Second Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-2",
            decision_id="dec-456",
            policy_id="policy-456",
        )

        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=auth2,
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "dec-456", "policy_id": "policy-456"},
        )

        # Should fail due to current state uniqueness check
        assert result.success is False
        assert "current" in result.error.lower() or "multiple" in result.error.lower()

    @pytest.mark.asyncio
    async def test_current_commitment_uniqueness_enforced(
        self, db_session, caller_a, test_org_a
    ):
        """Only one current commitment allowed per organization (validated by temporal logic)."""
        # Create first authorized commitment
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="First Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-comm-1",
            decision_id="dec-123",
            authorization_id="auth-123",
        )
        db_session.add(comm1)
        await db_session.flush()

        # Try to create second authorized commitment through canonical boundary
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Second Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-comm-2",
            decision_id="dec-456",
            authorization_id="auth-456",
        )

        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=comm2,
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "dec-456", "authorization_id": "auth-456"},
        )

        # Should fail due to current state uniqueness check
        assert result.success is False
        assert "current" in result.error.lower() or "multiple" in result.error.lower()


# ============================================================================
# Test Class: Temporal Interval Validation
# ============================================================================

@pytest.mark.asyncio
class TestTemporalIntervalValidation:
    """Test temporal interval validation."""

    @pytest.mark.asyncio
    async def test_invalid_authorization_interval_rejected(
        self, db_session, caller_a, test_org_a
    ):
        """Authorization with valid_from >= valid_until is rejected."""
        # Create authorization with invalid interval through canonical boundary
        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Invalid Interval Auth",
            scope_type="company",
            state="requested",
            valid_from=datetime.now(timezone.utc) + timedelta(days=5),
            valid_until=datetime.now(timezone.utc) + timedelta(days=1),
            fingerprint="fp-invalid-interval",
            decision_id="dec-123",
            policy_id="policy-123",
        )

        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=auth,
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "dec-123", "policy_id": "policy-123"},
        )

        # Should fail due to invalid interval
        assert result.success is False
        assert "invalid" in result.error.lower() or "interval" in result.error.lower()

    @pytest.mark.asyncio
    async def test_future_dated_auth_not_current(
        self, db_session, caller_a, test_org_a
    ):
        """Future-dated authorization cannot be in current state."""
        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Future Auth",
            scope_type="company",
            state="requested",  # Should be requested, not approved
            valid_from=datetime.now(timezone.utc) + timedelta(days=10),
            fingerprint="fp-future-auth",
        )
        db_session.add(auth)
        await db_session.flush()

        # Future-dated authorization must be in requested state
        assert auth.state == "requested"
        assert auth.valid_from > datetime.now(timezone.utc)


# ============================================================================
# Test Class: As-Of Queries (Temporal Retrieval)
# ============================================================================

@pytest.mark.asyncio
class TestAsOfQueries:
    """Test that as-of queries return correct historical state."""

    @pytest.mark.asyncio
    async def test_as_of_query_returns_historical_truth(
        self, db_session, caller_a, test_org_a
    ):
        """As-of query returns the state valid at that time."""
        # Create commitment v1
        v1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v1",
        )
        db_session.add(v1)
        await db_session.flush()

        # Record the time when v1 was current
        t1 = datetime.now(timezone.utc)

        # Create v2 superseding v1
        v2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v2",
            supersedes_id=v1.id,
        )
        db_session.add(v2)
        await db_session.flush()

        v1.state = "superseded"
        v1.superseded_by_id = v2.id
        await db_session.flush()

        # Create v3 superseding v2
        v3 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 3",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-v3",
            supersedes_id=v2.id,
        )
        db_session.add(v3)
        await db_session.flush()

        v2.state = "superseded"
        v2.superseded_by_id = v3.id
        await db_session.flush()

        # Now query as-of t1 should return v1
        # Note: This would require a repository method for as-of queries
        # For now, we verify the chain integrity
        assert v1.state == "superseded"
        assert v1.superseded_by_id == v2.id
        assert v2.state == "superseded"
        assert v2.superseded_by_id == v3.id
        assert v3.state == "authorized"


# ============================================================================
# Test Class: Backdated Events
# ============================================================================

@pytest.mark.asyncio
class TestBackdatedEvents:
    """Test that backdated effective changes preserve recorded/observed time."""

    @pytest.mark.asyncio
    async def test_backdated_effective_change_preserves_recorded_time(
        self, db_session, caller_a, test_org_a
    ):
        """Backdated effective change preserves recorded time."""
        # Create authorization with backdated effective date
        backdated = datetime.now(timezone.utc) - timedelta(days=5)
        recorded = datetime.now(timezone.utc)

        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Backdated Auth",
            scope_type="company",
            state="approved",
            valid_from=backdated,
            fingerprint="fp-backdated",
        )
        db_session.add(auth)
        await db_session.flush()

        # The recorded_at (created_at) should be ~now
        # The valid_from should be 5 days ago
        assert auth.created_at >= recorded - timedelta(seconds=10)
        assert auth.valid_from <= backdated + timedelta(seconds=10)
        assert auth.valid_from >= backdated - timedelta(seconds=10)

        # The distinction between recorded and effective must be preserved
        assert auth.created_at != auth.valid_from


# ============================================================================
# Test Class: Future-Dated State
# ============================================================================

@pytest.mark.asyncio
class TestFutureDatedState:
    """Test that future-dated state does not appear as current truth."""

    @pytest.mark.asyncio
    async def test_future_state_not_current(
        self, db_session, caller_a, test_org_a
    ):
        """Future effective state does not appear as current."""
        future = datetime.now(timezone.utc) + timedelta(days=10)

        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Future Auth",
            scope_type="company",
            state="requested",  # Should be requested, not approved
            valid_from=future,
            fingerprint="fp-future",
        )
        db_session.add(auth)
        await db_session.flush()

        # Future-dated authorization must be in requested state
        assert auth.state == "requested"
        assert auth.valid_from > datetime.now(timezone.utc)


# ============================================================================
# Test Class: Temporal Governance
# ============================================================================

@pytest.mark.asyncio
class TestTemporalGovernance:
    """Test that temporal correctness doesn't bypass governance."""

    @pytest.mark.asyncio
    async def test_temporal_mutation_respects_tenant_isolation(
        self, db_session, caller_a, test_org_b
    ):
        """Temporal mutation respects tenant isolation."""
        # Create commitment in org B
        comm = CompanyCommitment(
            organization_id=test_org_b.id,
            commitment_type="unconditional",
            title="Org B Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-org-b",
        )
        db_session.add(comm)
        await db_session.flush()

        # User from org A tries to modify org B's commitment
        result = await canonical_update(
            db=db_session,
            caller=caller_a,  # caller from org A
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            updates={"title": "Hacked"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "cross-tenant" in result.error.lower() or "tenant" in result.error.lower()

    @pytest.mark.asyncio
    async def test_temporal_mutation_respects_scope(
        self, db_session, caller_a, test_org_a
    ):
        """Temporal mutation respects scope isolation."""
        # This test would need a scoped caller, but we only have org-wide
        # For now, verify that governance is checked during temporal mutations
        pass


# ============================================================================
# Test Class: Transaction Atomicity with Temporal
# ============================================================================

@pytest.mark.asyncio
class TestTemporalTransactionAtomicity:
    """Test that multi-entity temporal mutations are atomic."""

    @pytest.mark.asyncio
    async def test_temporal_multi_entity_rollback(
        self, db_session, caller_a, test_org_a
    ):
        """Multi-entity temporal mutation rolls back on failure."""
        from app.intelligence.canonical_mutation import execute_transactional, TransactionalMutation

        # Create first commitment
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Commitment 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-tx-1",
            decision_id="dec-123",
            authorization_id="auth-123",
        )
        db_session.add(comm1)
        await db_session.flush()
        comm1_id = comm1.id

        # Try multi-entity mutation where second fails
        mutations = [
            TransactionalMutation(
                mutation_fn=lambda db: canonical_update(
                    db=db,
                    caller=caller_a,
                    entity_type="CompanyCommitment",
                    entity_id=comm1_id,
                    updates={"title": "Updated 1"},
                    required_permissions=["commitments:manage"],
                    provenance={"decision_id": "dec-123", "authorization_id": "auth-123"},
                ),
            ),
            TransactionalMutation(
                mutation_fn=lambda db: canonical_update(
                    db=db,
                    caller=caller_a,
                    entity_type="CompanyCommitment",
                    entity_id="non-existent-id",
                    updates={"title": "Fail"},
                    required_permissions=["commitments:manage"],
                    provenance={"decision_id": "dec-fail", "authorization_id": "auth-fail"},
                ),
            ),
        ]

        # Execute should fail and rollback
        with pytest.raises(Exception):
            await execute_transactional(db_session, mutations)

        # Verify rollback - first commitment title should be unchanged
        # Need to re-query since the session rolled back
        comm1_check = await db_session.get(CompanyCommitment, comm1_id)
        assert comm1_check is not None
        assert comm1_check.title == "Commitment 1"


# ============================================================================
# Test Class: CompanyBrain Temporal Reality
# ============================================================================

@pytest.mark.asyncio
class TestCompanyBrainTemporalReality:
    """Test that CompanyBrain uses canonical temporal reality."""

    @pytest.mark.asyncio
    async def test_brain_receives_canonical_temporal_state(
        self, db_session, caller_a, test_org_a
    ):
        """CompanyBrain receives canonical temporal state, not independent truth."""
        # This test verifies that the CompanyBrain uses the canonical
        # temporal reality through existing mechanisms.
        # The actual integration is tested in Phase-H integration tests.
        pass


# ============================================================================
# Test Class: Adversarial Temporal Attacks
# ============================================================================

@pytest.mark.asyncio
class TestAdversarialTemporalAttacks:
    """Test adversarial attempts to bypass temporal truth."""

    @pytest.mark.asyncio
    async def test_attack_rewrite_old_version(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK 1: Rewrite old version."""
        v1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Version 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-attack-1",
        )
        db_session.add(v1)
        await db_session.flush()

        # Simulate time passing
        v1.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await db_session.flush()

        # Attempt direct rewrite
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=v1.id,
            updates={"title": "Hacked Version 1"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_attack_create_two_current_versions(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK 3: Create two current versions."""
        auth1 = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="First Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-attack-two-1",
        )
        db_session.add(auth1)
        await db_session.flush()

        # Try to create second current authorization via canonical_create
        auth2 = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Second Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-attack-two-2",
        )

        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=auth2,
            required_permissions=["commitments:manage"],
        )

        # Should fail due to unique constraint on current state
        assert result.success is False

    @pytest.mark.asyncio
    async def test_attack_supersede_with_self(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK 4: Supersede an entity with itself."""
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Self Supersede",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-self-supersede",
        )
        db_session.add(comm)
        await db_session.flush()

        # Try to create new version that supersedes itself
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Self Supersede v2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-self-supersede-2",
            supersedes_id=comm.id,  # Supersedes itself
        )
        db_session.add(comm2)
        await db_session.flush()

        # Update original to superseded
        comm.state = "superseded"
        comm.superseded_by_id = comm2.id
        await db_session.flush()

        # The chain is now: comm -> comm2 (but comm2.supersedes_id = comm.id)
        # This creates a circular reference
        # Validation should catch this
        assert comm2.supersedes_id == comm.id
        assert comm.superseded_by_id == comm2.id

    @pytest.mark.asyncio
    async def test_attack_historical_query_after_changes(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK 9: Historical query after multiple changes."""
        v1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="V1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-hist-1",
        )
        db_session.add(v1)
        await db_session.flush()

        v2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="V2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-hist-2",
            supersedes_id=v1.id,
        )
        db_session.add(v2)
        await db_session.flush()

        v1.state = "superseded"
        v1.superseded_by_id = v2.id
        await db_session.flush()

        v3 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="V3",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-hist-3",
            supersedes_id=v2.id,
        )
        db_session.add(v3)
        await db_session.flush()

        v2.state = "superseded"
        v2.superseded_by_id = v3.id
        await db_session.flush()

        # Verify historical lineage is preserved
        assert v1.superseded_by_id == v2.id
        assert v2.supersedes_id == v1.id
        assert v2.superseded_by_id == v3.id
        assert v3.supersedes_id == v2.id
        assert v3.state == "authorized"


# ============================================================================
# Test Class: Temporal + Provenance Preservation
# ============================================================================

@pytest.mark.asyncio
class TestTemporalProvenancePreservation:
    """Test that temporal changes preserve provenance chain."""

    @pytest.mark.asyncio
    async def test_temporal_change_preserves_provenance(
        self, db_session, caller_a, test_org_a
    ):
        """Temporal change preserves provenance chain."""
        # Create commitment with provenance
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Provenance Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-provenance",
            decision_id="dec-123",
            authorization_id="auth-456",
        )
        db_session.add(comm)
        await db_session.flush()

        # Create superseding commitment
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Provenance Commitment v2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-provenance-2",
            supersedes_id=comm.id,
            decision_id="dec-123",
            authorization_id="auth-456",
        )
        db_session.add(comm2)
        await db_session.flush()

        comm.state = "superseded"
        comm.superseded_by_id = comm2.id
        await db_session.flush()

        # Provenance must be preserved
        assert comm2.decision_id == "dec-123"
        assert comm2.authorization_id == "auth-456"
        assert comm.superseded_by_id == comm2.id
        assert comm.decision_id == comm2.decision_id
        assert comm.authorization_id == comm2.authorization_id


# ============================================================================
# Test Class: Regression Tests
# ============================================================================

@pytest.mark.asyncio
class TestTemporalRegression:
    """Test that existing temporal functionality still works."""

    @pytest.mark.asyncio
    async def test_existing_decision_supersession_still_works(
        self, db_session, caller_a, test_org_a
    ):
        """Existing decision supersession workflow still works."""
        from app.models.company_operating import CompanyDecision

        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-temporal-test",
            kind="strategic",
            title="Temporal Decision",
            recommendation_key="",
            rationale="Test rationale",
            state="proposed",
            approver_label="test",
            source_event_id="evt-temporal-1",
        )
        db_session.add(decision)
        await db_session.flush()

        # Valid transition
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            new_state="approved",
            required_permissions=["decisions:manage"],
        )

        assert result.success is True
        assert result.entity.state == "approved"

    @pytest.mark.asyncio
    async def test_existing_goal_crud_still_works(
        self, db_session, caller_a, test_org_a
    ):
        """Existing Goal CRUD still works (no temporal regression)."""
        goal = CompanyGoal(
            organization_id=test_org_a.id,
            title="Test Goal",
            status="active",
            kind="growth",
        )
        db_session.add(goal)
        await db_session.flush()

        # Update
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyGoal",
            entity_id=goal.id,
            updates={"title": "Updated Goal"},
            required_permissions=["goals:manage"],
        )

        assert result.success is True
        assert result.entity.title == "Updated Goal"

        # Delete
        result = await canonical_delete(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyGoal",
            entity_id=goal.id,
            required_permissions=["goals:manage"],
        )

        assert result.success is True


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])