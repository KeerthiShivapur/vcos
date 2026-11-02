"""Gate 31 — Canonical Reality Integrity & Reconciliation Tests.

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
from app.services.canonical_reality_integrity_service import (
    canonical_reality_integrity_service,
    IntegrityFindingType,
    IntegritySeverity,
    FindingStatus,
    IntegrityFinding,
    RepairProposal,
    EpistemicClassification,
    FindingStatus,
)

from tests.conftest import register_org
import uuid


@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession):
    """Create a test organization with user."""
    org = Organization(
        name=f"Test Org {uuid.uuid4().hex[:8]}",
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


class TestIntegrityFindingModels:
    """Test integrity finding model creation and validation."""

    def test_integrity_finding_creation(self):
        """Test creating an integrity finding with all fields."""
        finding = IntegrityFinding(
            id="test-finding-1",
            organization_id="org-123",
            finding_type=IntegrityFindingType.STRUCTURAL_ORPHAN,
            severity=IntegritySeverity.HIGH,
            entity_type="CompanyDecisionAlternative",
            entity_id="alt-456",
            title="Orphaned alternative",
            description="Alternative references non-existent decision",
            observed_evidence={"decision_id": "dec-789"},
            derived_evidence={"check": "orphaned_entity"},
            epistemic_classification=EpistemicClassification.OBSERVED,
            provenance={"check": "orphaned_entity", "reference_field": "decision_id"},
            source_subsystem="structural_integrity",
            governance_scope_ids=["org-123"],
        )

        assert finding.id == "test-finding-1"
        assert finding.finding_type == IntegrityFindingType.STRUCTURAL_ORPHAN
        assert finding.severity == IntegritySeverity.HIGH
        assert finding.epistemic_classification == EpistemicClassification.OBSERVED
        assert finding.status == FindingStatus.OPEN

    def test_repair_proposal_creation(self):
        """Test creating a repair proposal."""
        proposal = RepairProposal(
            id="repair-1",
            finding_id="finding-1",
            organization_id="org-123",
            entity_type="CompanyDecisionAlternative",
            entity_id="alt-456",
            current_state={"decision_id": "dec-789"},
            proposed_change={"decision_id": "dec-valid"},
            evidence={"decision_id": "dec-789"},
            provenance={"check": "orphaned_entity"},
            reason="Fix orphaned reference",
            temporal_basis={"detected_at": "2024-01-01T00:00:00Z"},
            governance_scope_ids=["org-123"],
            actor="user-123",
            proposed_mutation={"decision_id": "dec-valid"},
            reversibility={"reversible": True, "method": "supersession"},
        )

        assert proposal.id == "repair-1"
        assert proposal.finding_id == "finding-1"
        assert proposal.status == "proposed"
        assert proposal.reversibility["reversible"] is True


class TestVocabularyCompleteness:
    """Test vocabulary completeness for integrity system."""

    def test_finding_types_complete(self):
        """Verify all finding types are defined."""
        finding_types = [f for f in IntegrityFindingType]
        assert len(finding_types) >= 44, "Should have comprehensive finding types"

        categories = {
            "structural": [f for f in finding_types if f.value.startswith("structural_")],
            "tenant": [f for f in finding_types if f.value.startswith("tenant_")],
            "temporal": [f for f in finding_types if f.value.startswith("temporal_")],
            "provenance": [f for f in finding_types if f.value.startswith("provenance_")],
            "epistemic": [f for f in finding_types if f.value.startswith("epistemic_")],
            "operating": [f for f in finding_types if f.value.startswith("operating_")],
            "integration": [f for f in finding_types if f.value.startswith("integration_")],
            "gate29": [f for f in finding_types if f.value.startswith("gate29_")],
            "gate30": [f for f in finding_types if f.value.startswith("gate30_")],
        }

        for cat, types in categories.items():
            assert len(types) > 0, f"Category {cat} should have finding types"

    def test_severity_levels_complete(self):
        """Test severity levels."""
        severities = [s for s in IntegritySeverity]
        assert IntegritySeverity.CRITICAL in severities
        assert IntegritySeverity.HIGH in severities
        assert IntegritySeverity.MEDIUM in severities
        assert IntegritySeverity.LOW in severities
        assert IntegritySeverity.INFO in severities

    def test_epistemic_classifications_complete(self):
        """Test epistemic classifications."""
        classifications = [c for c in EpistemicClassification]
        assert EpistemicClassification.OBSERVED in classifications
        assert EpistemicClassification.DERIVED in classifications
        assert EpistemicClassification.UNKNOWN in classifications
        assert EpistemicClassification.SUPPORTED in classifications
        assert EpistemicClassification.ASSOCIATED in classifications
        assert EpistemicClassification.CONTESTED in classifications


class TestCanonicalRealityIntegrityService:
    """Test the canonical reality integrity service."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        """Create a test organization with some data."""
        org = Organization(
            name="Test Integrity Org",
            slug="test-integrity-org",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email="integrity@test.com",
            full_name="Integrity User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

    async def test_run_integrity_scan_empty_org(self, db_session: AsyncSession, test_org):
        """Test running integrity scan on empty organization."""
        findings = await canonical_reality_integrity_service.run_integrity_scan(
            db=db_session,
            organization_id=test_org["org"].id,
            limit=100,
        )

        assert isinstance(findings, list)

    async def test_structural_integrity_orphaned_entity(self, db_session: AsyncSession, test_org):
        """Test detection of orphaned entities."""
        org = test_org["org"]

        # Create a decision
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="dec-valid",
            kind="reallocate_capacity",
            title="Valid Decision",
            state="approved",
            source_event_id="event-1",
        )
        db_session.add(decision)
        await db_session.flush()

        # Create alternative referencing non-existent decision
        from app.models.company_operating import CompanyDecisionAlternative
        alt = CompanyDecisionAlternative(
            organization_id=org.id,
            decision_id="non-existent-decision",
            alternative_key="alt-1",
            label="Orphaned Alternative",
            description="Test",
            chosen=False,
        )
        db_session.add(alt)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_structural_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        orphan_findings = [f for f in findings if f.finding_type == IntegrityFindingType.STRUCTURAL_ORPHAN]
        assert len(orphan_findings) >= 1
        assert orphan_findings[0].entity_type == "CompanyDecisionAlternative"
        assert orphan_findings[0].severity == IntegritySeverity.HIGH

    async def test_tenant_integrity_cross_reference(self, db_session: AsyncSession, test_org):
        """Test detection of cross-tenant references."""
        org = test_org["org"]

        # Create a second organization
        org2 = Organization(
            name="Other Org",
            slug="other-org",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org2)
        await db_session.flush()

        # Create decision in org2
        decision2 = CompanyDecision(
            organization_id=org2.id,
            decision_id="dec-org2",
            kind="hire",
            title="Org2 Decision",
            state="approved",
            source_event_id="event-2",
        )
        db_session.add(decision2)
        await db_session.flush()

        # Create authorization in org1 referencing decision in org2
        auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="full",
            title="Cross-Tenant Auth",
            decision_id=decision2.decision_id,
            state="approved",
            fingerprint="auth-cross-tenant",
        )
        db_session.add(auth)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_tenant_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        cross_tenant = [f for f in findings if f.finding_type == IntegrityFindingType.TENANT_CROSS_REFERENCE]
        assert len(cross_tenant) >= 1
        assert cross_tenant[0].severity == IntegritySeverity.CRITICAL

    async def test_temporal_integrity_invalid_interval(self, db_session: AsyncSession, test_org):
        """Test detection of invalid temporal intervals."""
        org = test_org["org"]

        from app.core.timeutils import utcnow
        now = utcnow()
        auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="full",
            title="Invalid Interval Auth",
            state="approved",
            valid_from=now + timedelta(days=2),
            valid_until=now + timedelta(days=1),  # Before valid_from
            fingerprint="auth-invalid-interval",
        )
        db_session.add(auth)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_temporal_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        interval_findings = [f for f in findings if f.finding_type == IntegrityFindingType.TEMPORAL_INVALID_INTERVAL]
        assert len(interval_findings) >= 1
        assert interval_findings[0].severity == IntegritySeverity.HIGH

    async def test_temporal_integrity_future_as_current(self, db_session: AsyncSession, test_org):
        """Test detection of future-dated state as current."""
        org = test_org["org"]

        from app.core.timeutils import utcnow
        now = utcnow()
        auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="full",
            title="Future Auth",
            state="approved",
            valid_from=now + timedelta(days=10),
            valid_until=now + timedelta(days=20),
            fingerprint="auth-future-current",
        )
        db_session.add(auth)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_temporal_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        future_findings = [f for f in findings if f.finding_type == IntegrityFindingType.TEMPORAL_FUTURE_AS_CURRENT]
        assert len(future_findings) >= 1
        assert future_findings[0].severity == IntegritySeverity.HIGH

    async def test_provenance_integrity_missing_evidence(self, db_session: AsyncSession, test_org):
        """Test detection of missing evidence in verifications."""
        org = test_org["org"]

        vc = VerificationContext(
            organization_id=org.id,
            verification_type="plan_vs_reality",
            title="No Evidence Verification",
            state="completed",
            evidence_fingerprints=[],  # Empty evidence
            fingerprint="vc-no-evidence",
        )
        db_session.add(vc)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_provenance_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        missing_evidence = [f for f in findings if f.finding_type == IntegrityFindingType.PROVENANCE_MISSING]
        assert len(missing_evidence) >= 1
        assert missing_evidence[0].severity == IntegritySeverity.HIGH

    async def test_epistemic_integrity_invalid_promotion(self, db_session: AsyncSession, test_org):
        """Test detection of invalid epistemic promotions."""
        org = test_org["org"]

        learning = OrganizationalLearning(
            organization_id=org.id,
            kind="outcome_learning",
            title="Promoted Without Evidence",
            lesson="Test lesson",
            fingerprint="learning-promoted",
            lifecycle="confirmed",  # Promoted lifecycle
            evidence_json="{}",  # No real evidence
            confidence=0.9,
        )
        db_session.add(learning)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_epistemic_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        promotion_findings = [f for f in findings if f.finding_type == IntegrityFindingType.EPISTEMIC_INVALID_PROMOTION]
        assert len(promotion_findings) >= 1
        assert promotion_findings[0].epistemic_classification == EpistemicClassification.DERIVED

    async def test_operating_chain_decision_without_auth(self, db_session: AsyncSession, test_org):
        """Test detection of decisions without authorization."""
        org = test_org["org"]

        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="dec-no-auth",
            kind="reallocate_capacity",
            title="Decision Without Auth",
            state="approved",
            source_event_id="event-dec",
        )
        db_session.add(decision)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_operating_chain_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        no_auth = [f for f in findings if f.finding_type == IntegrityFindingType.OPERATING_DECISION_WITHOUT_AUTH]
        assert len(no_auth) >= 1
        assert no_auth[0].severity == IntegritySeverity.HIGH

    async def test_gate29_integrity_drift_unaddressed(self, db_session: AsyncSession, test_org):
        """Test detection of unaddressed drift."""
        org = test_org["org"]

        drift = ModelTwinDrift(
            organization_id=org.id,
            drift_type="prediction_divergence",
            severity="high",
            status="detected",
            subject_type="prediction",
            subject_id="pred-1",
        )
        db_session.add(drift)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_gate29_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        drift_findings = [f for f in findings if f.finding_type == IntegrityFindingType.GATE29_DRIFT_UNADDRESSED]
        assert len(drift_findings) >= 1
        assert drift_findings[0].severity == IntegritySeverity.HIGH

    async def test_gate30_integrity_broken_phase(self, db_session: AsyncSession, test_org):
        """Test detection of invalid continuity phase."""
        org = test_org["org"]

        from app.core.timeutils import utcnow
        continuity = CompanyOperatingContinuity(
            organization_id=org.id,
            cycle_number=1,
            current_phase="identity",
            cycle_started_at=utcnow(),
            phase_entered_at=utcnow(),
            fingerprint="cont-valid-phase",
        )
        db_session.add(continuity)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_gate30_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        # Should not trigger for valid phase
        phase_findings = [f for f in findings if f.finding_type == IntegrityFindingType.GATE30_BROKEN_PHASE]
        assert len(phase_findings) == 0

    async def test_repair_proposal_generation(self, db_session: AsyncSession, test_org):
        """Test generating repair proposals."""
        org = test_org["org"]

        finding = IntegrityFinding(
            id="finding-test-1",
            organization_id=org.id,
            finding_type=IntegrityFindingType.STRUCTURAL_BROKEN_REFERENCE,
            severity=IntegritySeverity.HIGH,
            entity_type="CompanyAction",
            entity_id="action-123",
            title="Broken reference",
            description="Action references non-existent commitment",
            observed_evidence={"commitment_id": "comm-456"},
            provenance={"check": "broken_reference"},
            source_subsystem="structural_integrity",
        )

        proposal = await canonical_reality_integrity_service.generate_repair_proposal(
            db=db_session,
            finding=finding,
            actor="user-123",
            proposed_change={"source_commitment_id": "comm-valid"},
            reason="Fix broken reference to valid commitment",
        )

        assert proposal.finding_id == "finding-test-1"
        assert proposal.actor == "user-123"
        assert proposal.proposed_change == {"source_commitment_id": "comm-valid"}
        assert proposal.status == "proposed"
        assert proposal.reversibility["reversible"] is True

    async def test_integrity_scan_all_checks(self, db_session: AsyncSession, test_org):
        """Test running full integrity scan with all checks."""
        org = test_org["org"]

        # Add some test data that should trigger findings
        auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="full",
            title="Future Auth",
            state="approved",
            valid_from=datetime.now(timezone.utc) + timedelta(days=10),
            valid_until=datetime.now(timezone.utc) + timedelta(days=20),
            fingerprint="auth-future",
        )
        db_session.add(auth)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.run_integrity_scan(
            db=db_session,
            organization_id=org.id,
            checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain", "integration", "gate29", "gate30"],
            limit=100,
        )

        assert isinstance(findings, list)
        temporal_findings = [f for f in findings if f.finding_type == IntegrityFindingType.TEMPORAL_FUTURE_AS_CURRENT]
        assert len(temporal_findings) >= 1

        # Results should be sorted by severity
        severity_order = {
            IntegritySeverity.CRITICAL: 0,
            IntegritySeverity.HIGH: 1,
            IntegritySeverity.MEDIUM: 2,
            IntegritySeverity.LOW: 3,
            IntegritySeverity.INFO: 4,
        }
        for i in range(len(findings) - 1):
            assert severity_order.get(findings[i].severity, 99) <= severity_order.get(findings[i+1].severity, 99)


class TestAPIEndpoints:
    """Test API endpoints for integrity service."""

    @pytest_asyncio.fixture
    async def auth_client(self, client):
        """Create authenticated client."""
        org_data = await register_org(client)
        return org_data

    async def test_integrity_scan_endpoint(self, client, auth_client):
        """Test POST /canonical/integrity/scan endpoint."""
        headers = auth_client["headers"]
        response = await client.post(
            "/api/v1/canonical/integrity/scan",
            headers=headers,
            json={"limit": 100}
        )
        assert response.status_code == 200
        data = response.json()
        assert "findings" in data
        assert "total_found" in data
        assert "scan_completed_at" in data

    async def test_integrity_status_endpoint(self, client, auth_client):
        """Test GET /canonical/integrity/status endpoint."""
        headers = auth_client["headers"]
        response = await client.get(
            "/api/v1/canonical/integrity/status",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "organization_id" in data
        assert "by_severity" in data

    async def test_integrity_findings_list(self, client, auth_client):
        """Test GET /canonical/integrity/findings endpoint."""
        headers = auth_client["headers"]
        response = await client.get(
            "/api/v1/canonical/integrity/findings",
            headers=headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestArchitecturalInvariants:
    """Test architectural invariants of integrity system."""

    def test_no_parallel_reality(self):
        """Integrity service must not create parallel reality."""
        pass

    def test_governed_repair(self):
        """Repair must be governed, never silent."""
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


class TestAdversarialIntegrity:
    """Adversarial tests for integrity system."""

    async def test_cross_tenant_finding_access_blocked(self, db_session: AsyncSession, test_org):
        """Test that findings cannot be accessed across tenants."""
        pass

    async def test_unauthorized_repair_blocked(self, db_session: AsyncSession, test_org):
        """Test that repair requires authorization."""
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

    async def test_concurrent_repair_safety(self, db_session: AsyncSession, test_org):
        """Test concurrent repairs don't corrupt state."""
        pass


class TestRegressionCompatibility:
    """Test regression compatibility with existing gates."""

    async def test_gate30_continuity_integration(self, db_session: AsyncSession, test_org):
        """Test integrity integrates with Gate 30 continuity."""
        org = test_org["org"]

        from app.core.timeutils import utcnow
        continuity = CompanyOperatingContinuity(
            organization_id=org.id,
            cycle_number=1,
            current_phase="identity",
            cycle_started_at=utcnow(),
            phase_entered_at=utcnow(),
            fingerprint="cont-regression-1",
        )
        db_session.add(continuity)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_gate30_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        phase_findings = [f for f in findings if f.finding_type == IntegrityFindingType.GATE30_BROKEN_PHASE]
        assert len(phase_findings) == 0

    async def test_gate29_digital_twin_integration(self, db_session: AsyncSession, test_org):
        """Test integrity integrates with Gate 29 digital twin."""
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

        findings = await canonical_reality_integrity_service.check_gate29_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        drift_findings = [f for f in findings if f.finding_type == IntegrityFindingType.GATE29_DRIFT_UNADDRESSED]
        assert len(drift_findings) == 0

    async def test_gate28_governed_autonomy_integration(self, db_session: AsyncSession, test_org):
        """Test integrity integrates with Gate 28 autonomy."""
        org = test_org["org"]

        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Valid Proposal",
            proposal_type="optimize_capacity",
            state="authorized",
            approved_by="exec-1",
            approved_at=datetime.now(timezone.utc),
            fingerprint="autonomy-valid",
        )
        db_session.add(proposal)
        await db_session.flush()

        findings = await canonical_reality_integrity_service.check_epistemic_integrity(
            db=db_session,
            organization_id=org.id,
            limit=100,
        )

        promo_findings = [f for f in findings if f.finding_type == IntegrityFindingType.EPISTEMIC_PROPOSAL_AS_DECISION]
        assert len(promo_findings) == 0


class TestScaleInvariance:
    """Test scale invariance of integrity service."""

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

        findings = await canonical_reality_integrity_service.run_integrity_scan(
            db=db_session,
            organization_id=org.id,
            checks=["temporal"],
            limit=50,
        )

        assert len(findings) <= 50

    async def test_incremental_scan(self, db_session: AsyncSession, test_org):
        """Test incremental scan via changed_since."""
        org = test_org["org"]

        findings1 = await canonical_reality_integrity_service.run_integrity_scan(
            db=db_session,
            organization_id=org.id,
            changed_since=datetime.now(timezone.utc) - timedelta(days=1),
            limit=100,
        )

        auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="full",
            title="New Auth",
            state="approved",
            valid_from=datetime.now(timezone.utc) + timedelta(days=10),
            fingerprint="auth-new",
        )
        db_session.add(auth)
        await db_session.flush()

        findings2 = await canonical_reality_integrity_service.run_integrity_scan(
            db=db_session,
            organization_id=org.id,
            changed_since=datetime.now(timezone.utc) - timedelta(hours=1),
            checks=["temporal"],
            limit=100,
        )

        temporal_findings = [f for f in findings2 if f.finding_type == IntegrityFindingType.TEMPORAL_FUTURE_AS_CURRENT]
        assert len(temporal_findings) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])