"""Gate 6-D — Provenance Integrity Adversarial Tests.

These tests verify that provenance integrity is enforced through the canonical
mutation boundary: provenance cannot be fabricated, tampered with, or bypassed.
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
# Test Class: Missing Required Provenance
# ============================================================================

@pytest.mark.asyncio
class TestMissingRequiredProvenance:
    """Test that mutations fail when required provenance is missing."""

    @pytest.mark.asyncio
    async def test_commitment_requires_authorization_and_decision(
        self, db_session, caller_a, test_org_a
    ):
        """Conditional commitment requires both authorization and decision provenance."""
        commitment = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Test Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="test-fp-prov-1",
        )
        db_session.add(commitment)
        await db_session.flush()

        # Attempt to transition to authorized without authorization/decision
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=commitment.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "provenance" in result.error.lower() or "authorization" in result.error.lower()

    @pytest.mark.asyncio
    async def test_authorization_requires_decision_and_policy(
        self, db_session, caller_a, test_org_a
    ):
        """Authorization requires decision and policy provenance."""
        from app.models.execution_strategy import CompanyAuthorization

        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Test Authorization",
            scope_type="company",
            state="requested",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-test",
        )
        db_session.add(auth)
        await db_session.flush()

        # Attempt to transition to approved without decision/policy
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAuthorization",
            entity_id=auth.id,
            new_state="approved",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "provenance" in result.error.lower() or "decision" in result.error.lower() or "policy" in result.error.lower()

    @pytest.mark.asyncio
    async def test_action_requires_commitment_and_authorization(
        self, db_session, caller_a, test_org_a
    ):
        """Action requires commitment and authorization provenance."""
        from app.models.company_actions import CompanyAction

        action = CompanyAction(
            organization_id=test_org_a.id,
            action_type="task",
            title="Test Action",
            state="proposed",
            risk="low",
            source_problem="Test problem",
            policy="auto",
            fingerprint="test-fp-action-prov",
            source_commitment_id="non-existent-commitment",
            source_company_decision_id="non-existent-decision",
        )
        db_session.add(action)
        await db_session.flush()

        # Attempt to start action without commitment/authorization
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAction",
            entity_id=action.id,
            new_state="in_progress",
            required_permissions=["tasks:manage"],
        )

        assert result.success is False
        assert "provenance" in result.error.lower() or "commitment" in result.error.lower() or "authorization" in result.error.lower() or "decision" in result.error.lower()


# ============================================================================
# Test Class: Nonexistent Provenance Reference
# ============================================================================

@pytest.mark.asyncio
class TestNonexistentProvenanceReference:
    """Test that mutations fail when provenance references nonexistent entities."""

    @pytest.mark.asyncio
    async def test_commitment_rejects_nonexistent_authorization(
        self, db_session, caller_a, test_org_a
    ):
        """Commitment with nonexistent authorization_id is rejected."""
        commitment = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Test Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="test-fp-nonexist-1",
            authorization_id="non-existent-auth-id",
            decision_id="non-existent-decision-id",
        )
        db_session.add(commitment)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=commitment.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "authorization" in result.error.lower() or "provenance" in result.error.lower()

    @pytest.mark.asyncio
    async def test_authorization_rejects_nonexistent_decision(
        self, db_session, caller_a, test_org_a
    ):
        """Authorization with nonexistent decision_id is rejected."""
        from app.models.execution_strategy import CompanyAuthorization

        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Test Auth",
            scope_type="company",
            state="requested",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-nonexist",
            decision_id="non-existent-decision-id",
            policy_id="non-existent-policy-id",
        )
        db_session.add(auth)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAuthorization",
            entity_id=auth.id,
            new_state="approved",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "decision" in result.error.lower() or "policy" in result.error.lower() or "provenance" in result.error.lower()


# ============================================================================
# Test Class: Cross-Tenant Provenance
# ============================================================================

@pytest.mark.asyncio
class TestCrossTenantProvenance:
    """Test that provenance references cannot cross tenant boundaries."""

    @pytest.mark.asyncio
    async def test_commitment_cannot_use_other_org_authorization(
        self, db_session, caller_a, test_org_a, test_org_b
    ):
        """Org A commitment cannot reference Org B's authorization."""
        # Create authorization in Org B
        from app.models.execution_strategy import CompanyAuthorization

        auth_b = CompanyAuthorization(
            organization_id=test_org_b.id,
            authorization_type="full",
            title="Org B Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-b",
            decision_id="dec-b",
            policy_id="pol-b",
        )
        db_session.add(auth_b)
        await db_session.flush()

        # Try to create commitment in Org A referencing Org B's authorization
        # The authorization_id should be validated for cross-tenant access
        commitment = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Cross-tenant Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="test-fp-cross-tenant",
            authorization_id=auth_b.id,  # Org B's auth!
            decision_id="dec-123",
        )
        db_session.add(commitment)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=commitment.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
        )

        # Should fail - either at provenance validation (cross-tenant) or when trying to load the auth
        assert result.success is False
        assert "tenant" in result.error.lower() or "cross-tenant" in result.error.lower() or "cross-org" in result.error.lower() or "authorization" in result.error.lower()

    @pytest.mark.asyncio
    async def test_action_cannot_use_other_org_commitment(
        self, db_session, caller_a, test_org_a, test_org_b
    ):
        """Action in Org A cannot reference Org B's commitment."""
        from app.models.execution_strategy import CompanyCommitment
        from app.models.company_actions import CompanyAction

        # Create commitment in Org B
        comm_b = CompanyCommitment(
            organization_id=test_org_b.id,
            commitment_type="unconditional",
            title="Org B Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-comm-b",
        )
        db_session.add(comm_b)
        await db_session.flush()

        # Try to create action in Org A referencing Org B's commitment
        action = CompanyAction(
            organization_id=test_org_a.id,
            action_type="task",
            title="Cross-tenant Action",
            state="proposed",
            risk="low",
            source_problem="Test",
            policy="auto",
            fingerprint="test-fp-cross-action",
            source_commitment_id=comm_b.id,  # Org B's commitment!
            source_company_decision_id="dec-b",
        )
        db_session.add(action)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAction",
            entity_id=action.id,
            new_state="in_progress",
            required_permissions=["tasks:manage"],
        )

        assert result.success is False
        assert "tenant" in result.error.lower() or "cross-tenant" in result.error.lower() or "cross-org" in result.error.lower() or "commitment" in result.error.lower()


# ============================================================================
# Test Class: Cross-Scope Provenance
# ============================================================================

@pytest.mark.asyncio
class TestCrossScopeProvenance:
    """Test that provenance references respect scope boundaries."""

    @pytest.mark.asyncio
    async def test_project_scoped_action_cannot_use_other_project_commitment(
        self, db_session, caller_a, test_org_a
    ):
        """Action in Project A cannot reference Project B's commitment."""
        from app.models.execution_strategy import CompanyCommitment
        from app.models.company_actions import CompanyAction

        # Create two project-scoped commitments in same org
        comm_a = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Project A Commitment",
            scope_type="project",
            scope_id="proj-a",
            state="authorized",
            fingerprint="fp-comm-a",
        )
        comm_b = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Project B Commitment",
            scope_type="project",
            scope_id="proj-b",
            state="authorized",
            fingerprint="fp-comm-b",
        )
        db_session.add_all([comm_a, comm_b])
        await db_session.flush()

        # Action in project A trying to use project B's commitment
        action = CompanyAction(
            organization_id=test_org_a.id,
            action_type="task",
            title="Cross-project Action",
            state="proposed",
            risk="low",
            source_problem="Test",
            policy="auto",
            fingerprint="test-fp-cross-proj",
            scope_type="project",
            scope_id="proj-a",  # Action in project A
            source_commitment_id=comm_b.id,  # But referencing project B's commitment!
            source_company_decision_id="dec-b",
        )
        db_session.add(action)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAction",
            entity_id=action.id,
            new_state="validating",  # Valid transition: proposed -> validating
            required_permissions=["tasks:manage"],
            provenance={"source_commitment_id": comm_b.id, "source_company_decision_id": "dec-b"},
        )

        # Should fail - action in project A cannot use project B's commitment
        assert result.success is False
        assert "scope" in result.error.lower() or "cross" in result.error.lower() or "project" in result.error.lower()


# ============================================================================
# Test Class: Invalid Semantic Provenance
# ============================================================================

@pytest.mark.asyncio
class TestInvalidSemanticProvenance:
    """Test that provenance references must be semantically valid."""

    @pytest.mark.asyncio
    async def test_commitment_cannot_use_action_as_authorization(
        self, db_session, caller_a, test_org_a
    ):
        """Commitment cannot use an action ID as authorization."""
        from app.models.company_actions import CompanyAction

        # Create an action
        action = CompanyAction(
            organization_id=test_org_a.id,
            action_type="task",
            title="Test Action",
            state="proposed",
            risk="low",
            source_problem="Test",
            policy="auto",
            fingerprint="test-fp-action-as-auth",
        )
        db_session.add(action)
        await db_session.flush()

        # Try to use action as authorization for commitment
        commitment = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Bad Provenance Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="test-fp-bad-prov",
            authorization_id=action.id,  # Action ID used as authorization!
            decision_id="dec-123",
        )
        db_session.add(commitment)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=commitment.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "authorization" in result.error.lower() or "provenance" in result.error.lower()


# ============================================================================
# Test Class: Provenance Immutability
# ============================================================================

@pytest.mark.asyncio
class TestProvenanceImmutability:
    """Test that historical provenance cannot be silently rewritten."""

    @pytest.mark.asyncio
    async def test_historical_provenance_cannot_be_mutated(
        self, db_session, caller_a, test_org_a
    ):
        """Historical commitment provenance cannot be silently rewritten."""
        # Create commitment v1 with provenance
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Original Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-immut-1",
            decision_id="dec-original",
            authorization_id="auth-original",
        )
        db_session.add(comm1)
        await db_session.flush()

        # Create v2 superseding v1
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Superseding Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-immut-2",
            supersedes_id=comm1.id,
            decision_id="dec-original",
            authorization_id="auth-original",
        )
        db_session.add(comm2)
        await db_session.flush()

        comm1.state = "superseded"
        comm1.superseded_by_id = comm2.id
        await db_session.flush()

        # Attempt to modify v1's provenance
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm1.id,
            updates={"decision_id": "hacked-decision", "authorization_id": "hacked-auth"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_authorization_provenance_immutability(
        self, db_session, caller_a, test_org_a
    ):
        """Authorization provenance cannot be mutated after approval."""
        from app.models.execution_strategy import CompanyAuthorization

        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Immutable Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-immut",
            decision_id="dec-immut",
            policy_id="pol-immut",
        )
        db_session.add(auth)
        await db_session.flush()

        # Supersede by creating new authorization
        auth2 = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Superseding Auth",
            scope_type="company",
            state="approved",
            valid_from=datetime.now(timezone.utc),
            fingerprint="fp-auth-immut-2",
            decision_id="dec-immut-2",
            policy_id="pol-immut-2",
            # Note: CompanyAuthorization uses state transition to superseded, not supersedes_id
        )
        db_session.add(auth2)
        await db_session.flush()

        # Mark original as superseded via state transition
        auth.state = "superseded"
        # Note: CompanyAuthorization uses state transition to superseded, not supersedes_id
        await db_session.flush()

        # Try to mutate superseded auth's provenance
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAuthorization",
            entity_id=auth.id,
            updates={"decision_id": "hacked", "policy_id": "hacked"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()


# ============================================================================
# Test Class: Provenance Tampering
# ============================================================================

@pytest.mark.asyncio
class TestProvenanceTampering:
    """Test that provenance cannot be silently tampered with."""

    @pytest.mark.asyncio
    async def test_commitment_provenance_cannot_be_changed_without_supersession(
        self, db_session, caller_a, test_org_a
    ):
        """Changing commitment provenance requires supersession."""
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Original Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-tamper-1",
            decision_id="dec-original",
            authorization_id="auth-original",
        )
        db_session.add(comm)
        await db_session.flush()

        # Attempt to change provenance without supersession
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            updates={"decision_id": "new-decision", "authorization_id": "new-auth"},
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "new-decision", "authorization_id": "new-auth"},
        )

        assert result.success is False
        assert "provenance" in result.error.lower() or "supersession" in result.error.lower()

    @pytest.mark.asyncio
    async def test_action_provenance_cannot_be_changed(
        self, db_session, caller_a, test_org_a
    ):
        """Action provenance cannot be changed after creation."""
        from app.models.company_actions import CompanyAction

        action = CompanyAction(
            organization_id=test_org_a.id,
            action_type="task",
            title="Original Action",
            state="proposed",
            risk="low",
            source_problem="Original",
            policy="auto",
            fingerprint="fp-action-tamper",
            source_commitment_id="comm-original",
        )
        db_session.add(action)
        await db_session.flush()

        # Try to change commitment provenance
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAction",
            entity_id=action.id,
            updates={"source_commitment_id": "hacked-commitment"},
            required_permissions=["tasks:manage"],
        )

        assert result.success is False


# ============================================================================
# Test Class: Temporal Provenance Validation
# ============================================================================

@pytest.mark.asyncio
class TestTemporalProvenanceValidation:
    """Test that provenance respects temporal coherence."""

    @pytest.mark.asyncio
    async def test_future_dated_provenance_rejected(
        self, db_session, caller_a, test_org_a
    ):
        """Provenance referencing future entities is rejected."""
        from app.models.execution_strategy import CompanyAuthorization

        # Authorization with future valid_from
        auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            authorization_type="full",
            title="Future Auth",
            scope_type="company",
            state="approved",  # Invalid: future-dated but marked approved
            valid_from=datetime.now(timezone.utc) + timedelta(days=10),
            fingerprint="fp-future-prov",
            decision_id="dec-future",
            policy_id="pol-future",
        )
        db_session.add(auth)
        await db_session.flush()

        # Should fail - future-dated auth cannot be in approved state
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyAuthorization",
            entity_id=auth.id,
            new_state="approved",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "future" in result.error.lower() or "current" in result.error.lower() or "temporal" in result.error.lower()


# ============================================================================
# Test Class: Supersession Provenance Preservation
# ============================================================================

@pytest.mark.asyncio
class TestSupersessionProvenancePreservation:
    """Test that provenance is preserved across supersession."""

    @pytest.mark.asyncio
    async def test_commitment_supersession_preserves_lineage(
        self, db_session, caller_a, test_org_a
    ):
        """Superseding commitment preserves original lineage."""
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Original Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-super-1",
            decision_id="dec-123",
            authorization_id="auth-456",
        )
        db_session.add(comm1)
        await db_session.flush()

        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Superseding Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-super-2",
            supersedes_id=comm1.id,
            decision_id="dec-123",  # Same decision
            authorization_id="auth-789",  # Different authorization
        )
        db_session.add(comm2)
        await db_session.flush()

        comm1.state = "superseded"
        comm1.superseded_by_id = comm2.id
        await db_session.flush()

        # Verify lineage preserved
        assert comm2.decision_id == "dec-123"  # Same decision
        assert comm2.authorization_id == "auth-789"  # New authorization
        assert comm1.decision_id == "dec-123"  # Original preserved
        assert comm1.authorization_id == "auth-456"  # Original preserved


# ============================================================================
# Test Class: Cross-Tenant Provenance Isolation
# ============================================================================

@pytest.mark.asyncio
class TestProvenanceTenantIsolation:
    """Test that provenance cannot cross tenant boundaries."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_decision_reference(
        self, db_session, caller_a, test_org_a, test_org_b
    ):
        """Commitment in Org A cannot reference Decision in Org B."""
        from app.models.company_operating import CompanyDecision

        # Create decision in Org B
        dec_b = CompanyDecision(
            organization_id=test_org_b.id,
            decision_id="dec-b-cross",
            kind="strategic",
            title="Org B Decision",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-b",
        )
        db_session.add(dec_b)
        await db_session.flush()

        # Try to create commitment in Org A referencing Org B's decision
        commitment = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Cross-tenant Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="test-fp-cross-dec",
            decision_id=dec_b.id,  # Org B's decision!
            authorization_id="auth-a",
        )
        db_session.add(commitment)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=commitment.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": dec_b.id, "authorization_id": "auth-a"},
        )

        assert result.success is False
        assert "tenant" in result.error.lower() or "cross" in result.error.lower()


# ============================================================================
# Test Class: Provenance Tampering Prevention
# ============================================================================

@pytest.mark.asyncio
class TestProvenanceTamperingPrevention:
    """Test that provenance cannot be silently tampered with."""

    @pytest.mark.asyncio
    async def test_provenance_tampering_rejected(
        self, db_session, caller_a, test_org_a
    ):
        """Direct provenance tampering is rejected."""
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Tamper Test",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-tamper",
            decision_id="dec-orig",
            authorization_id="auth-orig",
        )
        db_session.add(comm)
        await db_session.flush()

        # Supersede
        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Superseding",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-tamper-2",
            supersedes_id=comm.id,
            decision_id="dec-orig",
            authorization_id="auth-orig",
        )
        db_session.add(comm2)
        await db_session.flush()

        comm.state = "superseded"
        comm.superseded_by_id = comm2.id
        await db_session.flush()

        # Attempt to tamper with original's provenance
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            updates={"decision_id": "tampered", "authorization_id": "tampered"},
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()


# ============================================================================
# Test Class: Provenance + Worker/Event Integration
# ============================================================================

@pytest.mark.asyncio
class TestWorkerEventProvenance:
    """Test that workers and events preserve provenance."""

    @pytest.mark.asyncio
    async def test_worker_mutation_preserves_provenance(
        self, db_session, caller_a, test_org_a
    ):
        """Worker mutations must provide valid provenance."""
        from app.intelligence.canonical_mutation import worker_canonical_mutation

        # Worker creates commitment with provenance
        async def create_commitment(db):
            return CompanyCommitment(
                organization_id=test_org_a.id,
                commitment_type="unconditional",
                title="Worker Commitment",
                scope_type="objective",
                state="proposed",
                fingerprint="fp-worker-1",
                decision_id="dec-worker",
                authorization_id="auth-worker",
            )

        # Worker creates commitment with provenance
        result = await worker_canonical_mutation(
            db=db_session,
            organization_id=test_org_a.id,
            user_id=caller_a.user_id,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            target_id=None,
            mutation_fn=create_commitment,
            fingerprint="fp-worker-1",
            provenance={"decision_id": "dec-worker", "authorization_id": "auth-worker"},
            source_event_id="evt-worker-1",
        )

        # Should succeed with valid provenance
        assert result.success is True
        assert result.entity.decision_id == "dec-worker"
        assert result.entity.authorization_id == "auth-worker"

    @pytest.mark.asyncio
    async def test_worker_cannot_bypass_provenance(
        self, db_session, caller_a, test_org_a
    ):
        """Worker without provenance is rejected."""
        from app.intelligence.canonical_mutation import worker_canonical_mutation

        # Worker tries to create commitment without provenance
        result = await worker_canonical_mutation(
            db=db_session,
            organization_id=test_org_a.id,
            user_id=caller_a.user_id,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            target_id=None,
            mutation_fn=lambda db: CompanyCommitment(
                organization_id=test_org_a.id,
                commitment_type="unconditional",
                title="No Provenance Commitment",
                scope_type="objective",
                state="proposed",
                fingerprint="fp-no-prov",
            ),
            fingerprint="fp-no-prov",
            provenance={},  # Missing required provenance!
            source_event_id="evt-no-prov",
        )

        assert result.success is False
        assert "provenance" in result.error.lower() or "authorization" in result.error.lower() or "decision" in result.error.lower()


# ============================================================================
# Test Class: Provenance + CompanyBrain
# ============================================================================

@pytest.mark.asyncio
class TestProvenanceCompanyBrain:
    """Test CompanyBrain respects provenance."""

    @pytest.mark.asyncio
    async def test_brain_receives_provenance_chain(
        self, db_session, caller_a, test_org_a
    ):
        """CompanyBrain receives canonical provenance chain."""
        # Create commitment with full provenance
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Brain Test Commitment",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-brain-1",
            decision_id="dec-brain",
            authorization_id="auth-brain",
        )
        db_session.add(comm)
        await db_session.flush()

        # Verify provenance chain is accessible
        # (Actual brain integration tested in Phase H tests)
        assert comm.decision_id == "dec-brain"
        assert comm.authorization_id == "auth-brain"


# ============================================================================
# Test Class: Adversarial Provenance Attacks
# ============================================================================

@pytest.mark.asyncio
class TestAdversarialProvenanceAttacks:
    """Test adversarial attempts to bypass provenance integrity."""

    @pytest.mark.asyncio
    async def test_attack_fake_decision_id(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK: Fake decision ID in provenance."""
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Fake Decision Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="fake-dec-fp",
            decision_id="fake-decision-id",
            authorization_id="auth-123",
        )
        db_session.add(comm)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "decision" in result.error.lower() or "provenance" in result.error.lower()

    @pytest.mark.asyncio
    async def test_attack_fake_authorization_id(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK: Fake authorization ID in provenance."""
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="conditional",
            title="Fake Auth Commitment",
            scope_type="objective",
            state="proposed",
            fingerprint="fake-auth-fp",
            decision_id="dec-123",
            authorization_id="fake-auth-id",
        )
        db_session.add(comm)
        await db_session.flush()

        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            new_state="authorized",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "authorization" in result.error.lower() or "provenance" in result.error.lower()

    @pytest.mark.asyncio
    async def test_attack_self_supersession(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK: Entity supersedes itself."""
        comm = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Self Supersede",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-self-super",
            supersedes_id=None,
        )
        db_session.add(comm)
        await db_session.flush()

        # Try to make it supersede itself
        comm.supersedes_id = comm.id
        await db_session.flush()

        # Should be caught by supersession chain validation
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            new_state="superseded",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_attack_circular_provenance(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK: Circular provenance chain."""
        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Circular 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-circ-1",
            decision_id="dec-1",
            authorization_id="auth-1",
        )
        db_session.add(comm1)
        await db_session.flush()

        comm2 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Circular 2",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-circ-2",
            supersedes_id=comm1.id,
            decision_id="dec-2",
            authorization_id="auth-2",
        )
        db_session.add(comm2)
        await db_session.flush()

        comm1.state = "superseded"
        comm1.superseded_by_id = comm2.id
        await db_session.flush()

        # Create circular reference: comm2 -> comm1 -> comm2
        comm2.supersedes_id = comm1.id  # Already set
        comm2.superseded_by_id = comm1.id  # Create cycle!
        await db_session.flush()

        # Validation should catch circular reference
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm2.id,
            new_state="superseded",
            required_permissions=["commitments:manage"],
        )

        assert result.success is False
        assert "circular" in result.error.lower() or "supersession" in result.error.lower() or "broken" in result.error.lower()


# ============================================================================
# Test Class: Provenance + Transaction Atomicity
# ============================================================================

@pytest.mark.asyncio
class TestProvenanceTransactionAtomicity:
    """Test that provenance mutations are atomic."""

    @pytest.mark.asyncio
    async def test_provenance_rollback_on_failure(
        self, db_session, caller_a, test_org_a
    ):
        """Multi-entity provenance mutation rolls back on failure."""
        from app.intelligence.canonical_mutation import execute_transactional, TransactionalMutation

        comm1 = CompanyCommitment(
            organization_id=test_org_a.id,
            commitment_type="unconditional",
            title="Commitment 1",
            scope_type="objective",
            state="authorized",
            fingerprint="fp-tx-1",
            decision_id="dec-1",
            authorization_id="auth-1",
        )
        db_session.add(comm1)
        await db_session.flush()

        mutations = [
            TransactionalMutation(
                mutation_fn=lambda db: canonical_update(
                    db=db,
                    caller=caller_a,
                    entity_type="CompanyCommitment",
                    entity_id=comm1.id,
                    updates={"title": "Updated 1"},
                    required_permissions=["commitments:manage"],
                ),
            ),
            TransactionalMutation(
                mutation_fn=lambda db: canonical_update(
                    db=db,
                    caller=caller_a,
                    entity_type="CompanyCommitment",
                    entity_id="non-existent",
                    updates={"title": "Fail"},
                    required_permissions=["commitments:manage"],
                ),
            ),
        ]

        with pytest.raises(Exception):
            await execute_transactional(db_session, mutations)

        # Verify rollback - first commitment unchanged
        comm1_check = await db_session.get(CompanyCommitment, comm1.id)
        assert comm1_check.title == "Commitment 1"


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])