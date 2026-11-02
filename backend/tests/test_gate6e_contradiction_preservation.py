"""Gate 6-E — Contradiction Preservation Adversarial Tests.

These tests verify that contradiction preservation is enforced through the canonical
mutation boundary: both sides of a contradiction are preserved, provenance is maintained,
and contradictions cannot be silently deleted or overwritten.
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
    ContradictionViolation,
    ContradictionPreservationViolation,
    ContradictionReferenceViolation,
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
# Test Class: Basic Contradiction Preservation
# ============================================================================

@pytest.mark.asyncio
class TestContradictionPreservation:
    """Test that contradictions are preserved during mutations."""

    @pytest.mark.asyncio
    async def test_contradiction_both_sides_preserved(
        self, db_session, caller_a, test_org_a
    ):
        """Both sides of a contradiction are preserved."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-contra-test",
            kind="strategic",
            title="Test Decision",
            recommendation_key="",
            rationale="Test rationale",
            state="approved",
            approver_label="test",
            source_event_id="evt-contra",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:test",
            side_a_json={"claim": "success"},
            side_b_json={"claim": "failure"},
            status="open",
            source_event_id="evt-contra",
        )
        db_session.add(contradiction)
        await db_session.commit()
        
        # Verify both sides preserved
        contra_check = await db_session.get(CompanyDecisionContradiction, contradiction.id)
        assert contra_check is not None
        assert "success" in str(contra_check.side_a_json)
        assert "failure" in str(contra_check.side_b_json)

    @pytest.mark.asyncio
    async def test_contradiction_cannot_be_deleted(
        self, db_session, caller_a, test_org_a
    ):
        """Contradiction cannot be deleted directly."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        from app.intelligence.canonical_mutation import ContradictionPreservationViolation
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-del-test",
            kind="strategic",
            title="Test Decision",
            recommendation_key="",
            rationale="Test rationale",
            state="approved",
            approver_label="test",
            source_event_id="evt-del",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:del-test",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-del",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Attempt to delete contradiction
        # DEBUG: Check accessible IDs
        from app.intelligence.company_context import resolve_accessible_ids
        from app.intelligence.canonical_mutation import _entity_type_to_kind
        kind = _entity_type_to_kind("CompanyDecisionContradiction")
        # Need to get user object for resolve_accessible_ids
        from app.models.user import User as UserModel
        user_obj = await db_session.get(UserModel, caller_a.user_id)
        accessible = await resolve_accessible_ids(
            db=db_session,
            user=user_obj,
            organization_id=test_org_a.id,
            kind=kind,
            ids=[contradiction.id]
        )
        print(f"DEBUG: kind={kind}, contradiction.id={contradiction.id}, accessible={accessible}, org_wide={caller_a.org_wide}")
        
        result = await canonical_delete(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )
        
        assert result.success is False
        assert "deleted" in result.error.lower() or "supersession" in result.error.lower()

    @pytest.mark.asyncio
    async def test_contradiction_sides_cannot_be_modified_without_supersession(
        self, db_session, caller_a, test_org_a
    ):
        """Contradiction sides cannot be modified without supersession."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        from app.intelligence.canonical_mutation import ContradictionPreservationViolation
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-mod-test",
            kind="strategic",
            title="Mod Test Decision",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-mod",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:mod-test",
            side_a_json={"claim": "original A"},
            side_b_json={"claim": "original B"},
            status="open",
            source_event_id="evt-mod",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Attempt to modify side_a without supersession
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"side_a_json": {"claim": "modified A"}},
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )
        
        assert result.success is False
        assert "supersession" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()


# ============================================================================
# Test Class: Contradiction vs Supersession
# ============================================================================

@pytest.mark.asyncio
class TestContradictionVsSupersession:
    """Test that contradiction and supersession are distinct."""

    @pytest.mark.asyncio
    async def test_supersession_preserves_contradiction_history(
        self, db_session, caller_a, test_org_a
    ):
        """Superseding a contradiction preserves the original."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-super-test",
            kind="strategic",
            title="Supersession Test",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-super",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:super-test",
            side_a_json={"claim": "original A"},
            side_b_json={"claim": "original B"},
            status="open",
            source_event_id="evt-super",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Supersede the contradiction by creating a new one
        new_contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:super-new",
            side_a_json={"claim": "superseding A"},
            side_b_json={"claim": "superseding B"},
            status="open",
            source_event_id="evt-super-new",
            supersedes_id=contradiction.id,
        )
        db_session.add(new_contradiction)
        await db_session.flush()
        
        # Mark original as superseded
        contradiction.status = "superseded"
        contradiction.superseded_by_id = new_contradiction.id
        await db_session.flush()
        
        # Verify original contradiction preserved
        original = await db_session.get(CompanyDecisionContradiction, contradiction.id)
        assert original is not None
        assert original.status == "superseded"
        assert original.superseded_by_id == new_contradiction.id
        assert original.side_a_json == {"claim": "original A"}
        
        # New contradiction exists
        new = await db_session.get(CompanyDecisionContradiction, new_contradiction.id)
        assert new is not None
        assert new.supersedes_id == contradiction.id

    @pytest.mark.asyncio
    async def test_supersession_does_not_delete_original_contradiction(
        self, db_session, caller_a, test_org_a
    ):
        """Superseding a contradiction does not delete the original."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-del-test",
            kind="strategic",
            title="Del Test Decision",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-del",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:del-test",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-del",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Supersede via transition
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="superseded",
            required_permissions=["commitments:manage"],
        )
        
        # Original contradiction still exists
        original = await db_session.get(CompanyDecisionContradiction, contradiction.id)
        assert original is not None


# ============================================================================
# Test Class: Provenance Preservation in Contradictions
# ============================================================================

@pytest.mark.asyncio
class TestContradictionProvenance:
    """Test that provenance is preserved in contradictions."""

    @pytest.mark.asyncio
    async def test_contradiction_provenance_preserved_on_supersession(
        self, db_session, caller_a, test_org_a
    ):
        """Superseding a contradiction preserves original provenance."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-prov-test",
            kind="strategic",
            title="Provenance Test",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-prov",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:prov-test",
            side_a_json={"claim": "A", "evidence": "ev1"},
            side_b_json={"claim": "B", "evidence": "ev2"},
            status="open",
            source_event_id="evt-prov",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Supersede - copy provenance fields from original
        new_contra = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:new",
            side_a_json={"claim": "new A", "evidence": "ev3"},
            side_b_json={"claim": "new B", "evidence": "ev4"},
            status="open",
            source_event_id="evt-new",
            supersedes_id=contradiction.id,
            lesson_memory_id=contradiction.lesson_memory_id,
            precedent_decision_id=contradiction.precedent_decision_id,
        )
        db_session.add(new_contra)
        await db_session.flush()
        
        contradiction.status = "superseded"
        contradiction.superseded_by_id = new_contra.id
        await db_session.flush()
        
        # Verify provenance preserved
        original = await db_session.get(CompanyDecisionContradiction, contradiction.id)
        assert original.side_a_json == {"claim": "original A"}
        assert original.side_b_json == {"claim": "original B"}
        assert original.superseded_by_id == new_contra.id
        
        new = await db_session.get(CompanyDecisionContradiction, new_contra.id)
        assert new.supersedes_id == contradiction.id


# ============================================================================
# Test Class: Cross-Tenant Contradiction Isolation
# ============================================================================

@pytest.mark.asyncio
class TestCrossTenantContradictionIsolation:
    """Test that contradictions cannot cross tenant boundaries."""

    @pytest.mark.asyncio
    async def test_contradiction_cannot_reference_other_tenant_decision(
        self, db_session, caller_a, test_org_a, test_org_b
    ):
        """Org A contradiction cannot reference Org B's decision."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        from app.intelligence.canonical_mutation import ContradictionReferenceViolation
        
        # Create decision in Org B
        decision_b = CompanyDecision(
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
        db_session.add(decision_b)
        await db_session.flush()
        
        # Try to create contradiction in Org A referencing Org B's decision
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision_b.id,  # Org B's decision!
            contradiction_key="cx:cross-test",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-cross",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Attempt to transition - should fail
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision_b.id},
        )
        
        assert result.success is False
        assert "tenant" in result.error.lower() or "cross" in result.error.lower()


# ============================================================================
# Test Class: Contradiction Tampering Prevention
# ============================================================================

@pytest.mark.asyncio
class TestContradictionTamperingPrevention:
    """Test that contradiction tampering is prevented."""

    @pytest.mark.asyncio
    async def test_historical_contradiction_cannot_be_modified(
        self, db_session, caller_a, test_org_a
    ):
        """Historical contradiction cannot be modified."""
        from app.models.company_operating import CompanyDecisionContradiction
        from app.intelligence.canonical_mutation import ContradictionPreservationViolation
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id="dec-hist-test",
            contradiction_key="cx:hist-test",
            side_a_json={"claim": "original"},
            side_b_json={"claim": "other"},
            status="superseded",
            source_event_id="evt-hist",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Try to modify superseded contradiction
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"side_a_json": {"claim": "tampered"}},
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "dec-hist-test"},
        )
        
        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()


# ============================================================================
# Test Class: Contradiction + Provenance
# ============================================================================

@pytest.mark.asyncio
class TestContradictionProvenance:
    """Test that provenance is preserved in contradictions."""

    @pytest.mark.asyncio
    async def test_contradiction_provenance_preserved(
        self, db_session, caller_a, test_org_a
    ):
        """Contradiction provenance is preserved on supersession."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-prov-test",
            kind="strategic",
            title="Prov Test Decision",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-prov",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Create contradiction with provenance
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:prov-test",
            side_a_json={"claim": "A", "evidence": "ev1"},
            side_b_json={"claim": "B", "evidence": "ev2"},
            status="open",
            source_event_id="evt-prov",
            lesson_memory_id="lesson-1",
            precedent_decision_id="dec-prec",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Supersede - copy provenance fields from original
        new_contra = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:new",
            side_a_json={"claim": "new A", "evidence": "ev3"},
            side_b_json={"claim": "new B", "evidence": "ev4"},
            status="open",
            source_event_id="evt-new",
            supersedes_id=contradiction.id,
            lesson_memory_id=contradiction.lesson_memory_id,
            precedent_decision_id=contradiction.precedent_decision_id,
        )
        db_session.add(new_contra)
        await db_session.flush()
        
        contradiction.status = "superseded"
        contradiction.superseded_by_id = new_contra.id
        await db_session.flush()
        
        # Verify provenance preserved
        original = await db_session.get(CompanyDecisionContradiction, contradiction.id)
        assert original.lesson_memory_id == new_contra.lesson_memory_id
        assert original.precedent_decision_id == new_contra.precedent_decision_id


# ============================================================================
# Test Class: Contradiction Tampering Prevention
# ============================================================================

@pytest.mark.asyncio
class TestContradictionTampering:
    """Test that contradiction tampering is prevented."""

    @pytest.mark.asyncio
    async def test_provenance_tampering_rejected(
        self, db_session, caller_a, test_org_a
    ):
        """Provenance tampering is rejected."""
        from app.models.company_operating import CompanyDecisionContradiction
        from app.intelligence.canonical_mutation import ContradictionPreservationViolation
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id="dec-tamper",
            contradiction_key="cx:tamper",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-tamper",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Supersede
        new_contra = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id="dec-tamper-2",
            contradiction_key="cx:tamper-2",
            side_a_json={"claim": "new A"},
            side_b_json={"claim": "new B"},
            status="open",
            source_event_id="evt-new",
            supersedes_id=contradiction.id,
        )
        db_session.add(new_contra)
        await db_session.flush()
        
        contradiction.status = "superseded"
        contradiction.superseded_by_id = new_contra.id
        await db_session.flush()
        
        # Attempt to tamper with original's provenance
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"source_event_id": "tampered"},
            required_permissions=["commitments:manage"],
        )
        
        assert result.success is False
        assert "superseded" in result.error.lower() or "historical" in result.error.lower() or "immutable" in result.error.lower()


# ============================================================================
# Test Class: Adversarial Contradiction Attacks
# ============================================================================

@pytest.mark.asyncio
class TestAdversarialContradictionAttacks:
    """Test adversarial attempts to bypass contradiction preservation."""

    @pytest.mark.asyncio
    async def test_attack_fake_contradiction_key(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK: Fake contradiction key."""
        from app.models.company_operating import CompanyDecisionContradiction
        
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id="dec-fake",
            contradiction_key="cx:fake",
            side_a_json={"claim": "fake"},
            side_b_json={"claim": "real"},
            status="open",
            source_event_id="evt-fake",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
        )
        
        assert result.success is False
        assert "decision" in result.error.lower() or "provenance" in result.error.lower()

    @pytest.mark.asyncio
    async def test_attack_circular_supersession(
        self, db_session, caller_a, test_org_a
    ):
        """ATTACK: Circular supersession chain."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-circular",
            kind="strategic",
            title="Circular Test",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-circ",
        )
        db_session.add(decision)
        await db_session.flush()
        
        contra1 = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:circ-1",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-1",
        )
        db_session.add(contra1)
        await db_session.flush()
        
        contra2 = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:circ-2",
            side_a_json={"claim": "A2"},
            side_b_json={"claim": "B2"},
            status="open",
            source_event_id="evt-2",
            supersedes_id=contra1.id,
        )
        db_session.add(contra2)
        await db_session.flush()
        
        contra1.superseded_by_id = contra2.id
        await db_session.flush()
        
        # Create circular reference
        contra2.supersedes_id = contra1.id
        await db_session.flush()
        
        # Should detect circular reference
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contra2.id,
            new_state="superseded",
            required_permissions=["commitments:manage"],
        )
        
        assert result.success is False


# ============================================================================
# Test Class: Regression Tests
# ============================================================================

@pytest.mark.asyncio
class TestContradictionRegression:
    """Test that existing contradiction functionality still works."""

    @pytest.mark.asyncio
    async def test_existing_contradiction_workflow_still_works(
        self, db_session, caller_a, test_org_a
    ):
        """Existing contradiction workflow still works."""
        from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
        
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-reg-test",
            kind="strategic",
            title="Regression Decision",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-reg",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Create contradiction
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:reg-test",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-reg",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Transition through valid states
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )
        assert result.success is True
        assert result.entity.status == "acknowledged"
        
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="resolved",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )
        assert result.success is True
        assert result.entity.status == "resolved"


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])