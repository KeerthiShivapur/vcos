"""
Gate 6-F — Epistemic Integrity Adversarial Tests.

These tests verify that epistemic integrity is enforced through the canonical
mutation boundary: AI-generated content cannot silently become canonical facts,
evidence does not equal truth, provenance survives epistemic transitions,
and all epistemic promotion rules are enforced.
"""

import pytest
import pytest_asyncio
import uuid
import hashlib
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service
from app.intelligence.company_context import resolve_caller_access
from app.intelligence.canonical_mutation import (
    canonical_create,
    canonical_update,
    canonical_transition,
    canonical_delete,
    EpistemicStatus,
    EpistemicViolation,
    EpistemicPromotionViolation,
    AIOriginViolation,
    EvidenceTruthConfusionViolation,
    ProvenanceStrippingViolation,
    ContradictionPreservationViolation,
    validate_epistemic_boundary,
)
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecisionEvidence


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
async def test_user_limited(db_session, test_org_a):
    """Create test user in organization A WITHOUT ceo role (limited permissions)."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"test-user-limited-{unique}",
        email=f"user-limited-{unique}@test.com",
        full_name=f"Limited User {unique}",
        status="active",
        organization_id=test_org_a.id,
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def caller_a(db_session, test_user_a, test_org_a):
    """Create caller access for user A (org-wide with CEO role)."""
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org_a.id)

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
    """Create caller access for user B (org-wide with CEO role)."""
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org_b.id)

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


@pytest_asyncio.fixture
async def caller_limited(db_session, test_user_limited, test_org_a):
    """Create caller access for limited user (no CEO role)."""
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org_a.id)
    # Don't assign CEO role - user has limited permissions

    caller = await resolve_caller_access(
        db_session, organization_id=test_org_a.id, user=test_user_limited
    )
    return caller


# Helper to set epistemic status on decision after creation
def set_epistemic_status(decision, status: EpistemicStatus):
    """Set epistemic status on decision entity."""
    decision.epistemic_status = status


# ============================================================================
# Test Classes
# ============================================================================

class TestBasicEpistemicBoundary:
    """Test that basic epistemic promotion rules are enforced."""

    @pytest.mark.asyncio
    async def test_allowed_promotions_work(
        self, db_session, caller_a, test_org_a
    ):
        """Valid epistemic promotions should succeed."""
        from app.models.company_operating import CompanyDecision
        from app.intelligence.canonical_mutation import CanonicalMutationContext
        
        # Create a decision in the database
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            title="Test Decision for Epistemic Boundary",
            kind="operational",
            rationale="Test decision for epistemic boundary test",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        db_session.add(decision)
        await db_session.flush()
        
        context = CanonicalMutationContext(
            caller=caller_a,
            tenant_id=test_org_a.id,
            governance_scope_ids=caller_a.visible_scope_ids,
            permissions=await caller_a.get_permissions(db_session),
            target_entity_type="CompanyDecision",
            target_id=decision.id,
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        
        # OBSERVED -> MEASURED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.MEASURED)
        assert result is True
        # OBSERVED -> EVIDENCE_BACKED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.EVIDENCE_BACKED)
        assert result is True
        
        # Update entity in database to reflect current state
        decision.epistemic_status = EpistemicStatus.MEASURED
        db_session.add(decision)
        await db_session.flush()
        
        # Update context to reflect current state
        context.epistemic_status = EpistemicStatus.MEASURED
        # MEASURED -> EVIDENCE_BACKED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.EVIDENCE_BACKED)
        assert result is True
        
        # Update entity in database to reflect current state
        decision.epistemic_status = EpistemicStatus.EVIDENCE_BACKED
        db_session.add(decision)
        await db_session.flush()
        
        context.epistemic_status = EpistemicStatus.EVIDENCE_BACKED
        # EVIDENCE_BACKED -> INFERRED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.INFERRED)
        assert result is True
        
        # Update entity in database
        decision.epistemic_status = EpistemicStatus.INFERRED
        db_session.add(decision)
        await db_session.flush()
        
        context.epistemic_status = EpistemicStatus.INFERRED
        # INFERRED -> PREDICTED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.PREDICTED)
        assert result is True
        # INFERRED -> PROPOSED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.PROPOSED)
        assert result is True
        
        # Update entity in database
        decision.epistemic_status = EpistemicStatus.PREDICTED
        db_session.add(decision)
        await db_session.flush()
        
        context.epistemic_status = EpistemicStatus.PREDICTED
        # PREDICTED -> PROPOSED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.PROPOSED)
        assert result is True
        
        # Update entity in database
        decision.epistemic_status = EpistemicStatus.PROPOSED
        db_session.add(decision)
        await db_session.flush()
        
        context.epistemic_status = EpistemicStatus.PROPOSED
        # PROPOSED -> CONTESTED
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.CONTESTED)
        assert result is True

    @pytest.mark.asyncio
    async def test_illegal_promotions_blocked(
        self, db_session, caller_a, test_org_a
    ):
        """Invalid epistemic promotions should be rejected."""
        from app.models.company_operating import CompanyDecision
        from app.intelligence.canonical_mutation import CanonicalMutationContext
        
        # Create a decision in the database with OBSERVED status
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            title="Test Decision for Epistemic Boundary",
            kind="operational",
            rationale="Test decision for epistemic boundary test",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        db_session.add(decision)
        await db_session.flush()
        
        context = CanonicalMutationContext(
            caller=caller_a,
            tenant_id=test_org_a.id,
            governance_scope_ids=caller_a.visible_scope_ids,
            permissions=await caller_a.get_permissions(db_session),
            target_entity_type="CompanyDecision",
            target_id=decision.id,
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        
        # OBSERVED -> INFERRED (skip MEASURED/EVIDENCE_BACKED)
        with pytest.raises(EpistemicViolation):
            await validate_epistemic_boundary(db_session, context, EpistemicStatus.INFERRED)
        
        # OBSERVED -> PREDICTED (skip levels)
        with pytest.raises(EpistemicViolation):
            await validate_epistemic_boundary(db_session, context, EpistemicStatus.PREDICTED)
        
        # OBSERVED -> PROPOSED (skip levels)
        with pytest.raises(EpistemicViolation):
            await validate_epistemic_boundary(db_session, context, EpistemicStatus.PROPOSED)
        
        # OBSERVED -> CONTESTED (skip levels)
        with pytest.raises(EpistemicViolation):
            await validate_epistemic_boundary(db_session, context, EpistemicStatus.CONTESTED)
        
        # INFERRED -> OBSERVED (downgrade not allowed by default)
        # Create a new decision with INFERRED status
        decision2 = CompanyDecision(
            organization_id=test_org_a.id,
            title="Test Decision for Epistemic Boundary 2",
            kind="operational",
            rationale="Test decision for epistemic boundary test",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.INFERRED,
        )
        db_session.add(decision2)
        await db_session.flush()
        
        context2 = CanonicalMutationContext(
            caller=caller_a,
            tenant_id=test_org_a.id,
            governance_scope_ids=caller_a.visible_scope_ids,
            permissions=await caller_a.get_permissions(db_session),
            target_entity_type="CompanyDecision",
            target_id=decision2.id,
            epistemic_status=EpistemicStatus.INFERRED,
        )
        
        with pytest.raises(EpistemicViolation):
            await validate_epistemic_boundary(db_session, context2, EpistemicStatus.OBSERVED)
        
        # CONTESTED -> any promotion
        decision2 = CompanyDecision(
            organization_id=test_org_a.id,
            title="Test Decision for Epistemic Boundary 2",
            kind="operational",
            rationale="Test decision for epistemic boundary test",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.CONTESTED,
        )
        db_session.add(decision2)
        await db_session.flush()
        
        context2 = CanonicalMutationContext(
            caller=caller_a,
            tenant_id=test_org_a.id,
            governance_scope_ids=caller_a.visible_scope_ids,
            permissions=await caller_a.get_permissions(db_session),
            target_entity_type="CompanyDecision",
            target_id=decision2.id,
            epistemic_status=EpistemicStatus.CONTESTED,
        )
        
        with pytest.raises(EpistemicViolation):
            await validate_epistemic_boundary(db_session, context2, EpistemicStatus.OBSERVED)

    @pytest.mark.asyncio
    async def test_same_status_allowed(
        self, db_session, caller_a, test_org_a
    ):
        """Same epistemic status (no promotion) should be allowed."""
        from app.models.company_operating import CompanyDecision
        from app.intelligence.canonical_mutation import CanonicalMutationContext
        
        # Create a decision in the database
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            title="Test Decision for Epistemic Boundary",
            kind="operational",
            rationale="Test decision for epistemic boundary test",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        db_session.add(decision)
        await db_session.flush()
        
        context = CanonicalMutationContext(
            caller=caller_a,
            tenant_id=test_org_a.id,
            governance_scope_ids=caller_a.visible_scope_ids,
            permissions=await caller_a.get_permissions(db_session),
            target_entity_type="CompanyDecision",
            target_id=decision.id,
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        result = await validate_epistemic_boundary(db_session, context, EpistemicStatus.PROPOSED)
        assert result is True


class TestAIGeneratedContentTracking:
    """Test that AI-generated content cannot silently become canonical facts."""

    @pytest.mark.asyncio
    async def test_ai_content_requires_human_confirmation(
        self, db_session, caller_a, test_org_a
    ):
        """AI-generated content promoted to strong epistemic status requires human confirmation."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-ai-test",
            kind="strategic",
            title="AI Decision Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-ai",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.EVIDENCE_BACKED)

        # Attempt to create AI-generated decision with EVIDENCE_BACKED status
        # without human confirmation - should fail
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "ai_generated": True,
                "model_id": "gpt-4",
                "model_version": "1.0",
                "decision_id": decision.id,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "human confirmation" in result.error.lower() or "ai" in result.error.lower()

    @pytest.mark.asyncio
    async def test_ai_content_with_human_confirmation_succeeds(
        self, db_session, caller_a, test_org_a
    ):
        """AI-generated content with human confirmation should succeed."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-ai-confirmed",
            kind="strategic",
            title="AI Decision Confirmed",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-ai-confirmed",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.EVIDENCE_BACKED)

        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "ai_generated": True,
                "model_id": "gpt-4",
                "model_version": "1.0",
                "human_confirmed": True,
                "decision_id": decision.id,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True


class TestEvidenceVsTruth:
    """Test that evidence does not equal truth."""

    @pytest.mark.asyncio
    async def test_evidence_backed_cannot_become_observed_without_direct_observation(
        self, db_session, caller_a, test_org_a
    ):
        """Evidence-backed claim cannot become OBSERVED without direct observation."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-evidence-test",
            kind="strategic",
            title="Evidence Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-evidence",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.OBSERVED)

        # Create with evidence but try to promote to OBSERVED
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "evidence_ids": ["ev-1", "ev-2"],
                "supporting_evidence": "Strong evidence",
                "decision_id": decision.id,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "direct observation" in result.error.lower() or "evidence" in result.error.lower()

    @pytest.mark.asyncio
    async def test_evidence_backed_can_become_inferred(
        self, db_session, caller_a, test_org_a
    ):
        """Evidence-backed claim can become INFERRED (valid promotion path)."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-evidence-test",
            kind="strategic",
            title="Evidence Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-evidence",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.EVIDENCE_BACKED)
        
        # EVIDENCE_BACKED -> INFERRED (valid promotion)
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.INFERRED},
            provenance={
                "evidence_ids": ["ev-1", "ev-2"],
                "supporting_evidence": "Strong evidence",
                "decision_id": decision.id,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True


class TestProvenancePreservation:
    """Test that provenance survives epistemic transitions."""

    @pytest.mark.asyncio
    async def test_provenance_not_stripped_on_promotion(
        self, db_session, caller_a, test_org_a
    ):
        """Provenance fields must not be stripped during epistemic promotion."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-prov-test",
            kind="strategic",
            title="Provenance Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-prov",
        )
        db_session.add(decision)
        await db_session.flush()

        # Create with provenance
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "decision_id": decision.id,
                "source_event_id": "evt-prov",
                "evidence_ids": ["ev-1"],
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True

        # Now try to update without provenance - should fail
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"state": "approved"},
            provenance={},  # Empty provenance - should fail
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "provenance" in result.error.lower() or "strip" in result.error.lower()

    @pytest.mark.asyncio
    async def test_provenance_preserved_on_valid_promotion(
        self, db_session, caller_a, test_org_a
    ):
        """Valid epistemic promotion preserves provenance."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-prov-promote",
            kind="strategic",
            title="Provenance Promotion",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-prov-promote",
        )
        db_session.add(decision)
        await db_session.flush()

        # Create with provenance
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "decision_id": decision.id,
                "source_event_id": "evt-prov",
                "evidence_ids": ["ev-1"],
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True

        # Update with same provenance - should succeed
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"state": "approved"},
            provenance={
                "decision_id": decision.id,
                "source_event_id": "evt-prov-promote",
                "evidence_ids": ["ev-1"],
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True


class TestHistoricalEpistemicProtection:
    """Test that historical epistemic states are protected."""

    @pytest.mark.asyncio
    async def test_historical_promotion_requires_justification(
        self, db_session, caller_a, test_org_a
    ):
        """Historical entity promotion to EVIDENCE_BACKED requires justification."""
        # Create a decision with PROPOSED status
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-historical-test",
            kind="strategic",
            title="Historical Test",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-historical",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.PROPOSED)

        # Try to promote to EVIDENCE_BACKED (skipping MEASURED) without justification
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.EVIDENCE_BACKED},
            provenance={"decision_id": decision.id},
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "justification" in result.error.lower() or "epistemic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_historical_promotion_with_justification_succeeds(
        self, db_session, caller_a, test_org_a
    ):
        """Historical entity promotion to EVIDENCE_BACKED with justification succeeds."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-historical-justified",
            kind="strategic",
            title="Historical Justified",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-historical-justified",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.OBSERVED)

        # First promote to MEASURED (valid step from OBSERVED)
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.MEASURED},
            provenance={
                "decision_id": decision.id,
                "epistemic_justification": "New evidence discovered through audit",
            },
            required_permissions=["decisions:manage"],
        )
        assert result.success is True
        
        # Then promote to EVIDENCE_BACKED with justification
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.EVIDENCE_BACKED},
            provenance={
                "decision_id": decision.id,
                "epistemic_justification": "New evidence discovered through audit",
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True


class TestContradictionIntegration:
    """Test integration with contradiction preservation (Gate 6-E)."""

    @pytest.mark.asyncio
    async def test_promotion_blocked_by_open_contradiction(
        self, db_session, caller_a, test_org_a
    ):
        """Promotion to strong epistemic status blocked by open contradiction."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-contradiction-test",
            kind="strategic",
            title="Contradiction Test",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-contradiction",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.OBSERVED)

        # Create open contradiction
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:test",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-contradiction",
        )
        db_session.add(contradiction)
        await db_session.flush()

        # Try to promote from OBSERVED to MEASURED (valid promotion) with open contradiction
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.MEASURED},
            provenance={"decision_id": decision.id},
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "contradiction" in result.error.lower() or "resolution" in result.error.lower()

    @pytest.mark.asyncio
    async def test_promotion_with_contradiction_resolution_succeeds(
        self, db_session, caller_a, test_org_a
    ):
        """Promotion with explicit contradiction resolution succeeds."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-contradiction-resolved",
            kind="strategic",
            title="Contradiction Resolved",
            recommendation_key="",
            rationale="Test",
            state="approved",
            approver_label="test",
            source_event_id="evt-contradiction-resolved",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.OBSERVED)

        # Create open contradiction
        contradiction = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:resolved",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="acknowledged",
            source_event_id="evt-contradiction-resolved",
        )
        db_session.add(contradiction)
        await db_session.flush()

        # Promote to EVIDENCE_BACKED with contradiction resolution
        # First promote to MEASURED (valid step from OBSERVED)
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.MEASURED},
            provenance={
                "decision_id": decision.id,
                "contradiction_resolution": "Contradiction acknowledged and evidence reviewed",
            },
            required_permissions=["decisions:manage"],
        )
        assert result.success is True
        
        # Then promote to EVIDENCE_BACKED with contradiction resolution
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.EVIDENCE_BACKED},
            provenance={
                "decision_id": decision.id,
                "contradiction_resolution": "Contradiction acknowledged and evidence reviewed",
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True


class TestGovernanceAuthorization:
    """Test governance authorization for epistemic promotion."""

    @pytest.mark.asyncio
    async def test_promotion_requires_governance_permissions(
        self, db_session, test_org_a, caller_a
    ):
        """Strong epistemic promotions require governance permissions."""
        # Test that CEO caller (with all permissions) can create with EVIDENCE_BACKED
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-perm-test",
            kind="strategic",
            title="Perm Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-perm",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # CEO caller creates with EVIDENCE_BACKED - should succeed
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={"decision_id": decision.id},
            required_permissions=["decisions:manage"],
        )
        assert result.success is True
        
        # Now test that a caller without evidence:validate permission cannot promote to EVIDENCE_BACKED
        # The caller_a fixture has CEO role which includes all permissions
        # This test verifies the permission check exists in the code path
        # (The actual permission denial is tested via the canonical_mutation boundary)
        
        # Verify that the promotion to EVIDENCE_BACKED requires evidence:validate permission
        # by checking the validate_epistemic_integrity function directly
        from app.intelligence.canonical_mutation import validate_epistemic_integrity, CanonicalMutationContext, EpistemicStatus
        from app.intelligence.company_context import CallerAccess
        from app.models.user import User as UserModel
        
        # Create a mock caller without evidence:validate permission
        limited_user = User(id="test-limited", email="limited@test.com", organization_id=test_org_a.id)
        caller_limited = CallerAccess(
            organization_id=test_org_a.id,
            user_id="test-limited",
            employee_id=None,
            org_wide=False,
            anchored_scope_ids=frozenset(),
            ancestry_scope_ids=frozenset(),
            visible_scope_ids=frozenset(),
            project_ids=frozenset(),
            member_conversation_ids=frozenset(),
            links={},
        )
        
        context = CanonicalMutationContext(
            caller=caller_limited,
            tenant_id=test_org_a.id,
            governance_scope_ids=frozenset(),
            permissions=frozenset(["decisions:manage"]),  # Missing evidence:validate
            target_entity_type="CompanyDecision",
            target_id=None,
            epistemic_status=EpistemicStatus.EVIDENCE_BACKED,
        )
        
        # This should fail due to missing evidence:validate permission
        try:
            await validate_epistemic_integrity(db_session, context)
            assert False, "Should have raised EpistemicPromotionViolation"
        except Exception as e:
            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()

    
    
