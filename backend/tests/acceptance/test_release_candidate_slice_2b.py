"""Release Candidate Hardening — Slice 2B: Pre-release Canonical Fingerprint Tests.

Tests validate the canonical fingerprint system that deterministically represents
the pre-release canonical company state.
"""

import pytest
import pytest_asyncio
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from app.core.timeutils import utcnow
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.services.canonical_fingerprint import (
    canonical_fingerprint_service,
    release_candidate_fingerprint_service,
    CanonicalFingerprintService,
    ReleaseCandidateFingerprintService,
    CANONICAL_COMPONENTS,
    FingerprintComponent,
    FingerprintAlgorithm,
    FingerprintStatus,
    ComponentFingerprint,
    TenantFingerprint,
    ReleaseCandidateFingerprint,
    _normalize_value,
    _normalize_record,
)

def _gen_fp() -> str:
    """Generate a deterministic fingerprint for testing."""
    return hashlib.sha256(f"test-{uuid.uuid4().hex}".encode()).hexdigest()[:160]


def _gen_short_fp() -> str:
    """Generate a short fingerprint for testing."""
    return hashlib.sha256(f"test-{uuid.uuid4().hex}".encode()).hexdigest()[:64]
from app.models.organization import Organization
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role
from app.models.project import Project
from app.models.task import Task
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyAuthorization, CompanyCommitment, CompanyGoal
from app.models.company_actions import CompanyAction
from app.models.governance import ApprovalPolicy
from app.models.canonical_integration import ConnectorInstance
from app.models.longitudinal import CompanyTimelineEvent, CompanyKnowledgeSnapshot
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.services.release_safety_preflight import release_safety_preflight


class TestCanonicalNormalization:
    """Tests for deterministic normalization."""

    def test_normalize_datetime_utc(self):
        """UTC datetime normalizes to ISO format."""
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        result = _normalize_value(dt)
        assert result == "2024-01-15T10:30:45+00:00"

    def test_normalize_datetime_naive(self):
        """Naive datetime gets UTC timezone."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = _normalize_value(dt)
        assert result == "2024-01-15T10:30:45+00:00"

    def test_normalize_dict_sorted_keys(self):
        """Dict keys are sorted for determinism."""
        data = {"zebra": 1, "alpha": 2, "middle": 3}
        result = _normalize_value(data)
        keys = list(result.keys())
        assert keys == ["alpha", "middle", "zebra"]

    def test_normalize_list_sorted(self):
        """Lists are sorted for determinism."""
        data = [3, 1, 2]
        result = _normalize_value(data)
        assert result == [1, 2, 3]

    def test_normalize_record_excludes_secrets(self):
        """Secrets are excluded from normalization."""
        record = {
            "id": "test-1",
            "name": "Test",
            "password": "secret123",
            "api_key": "key-abc",
            "token": "bearer-xyz",
        }
        result = _normalize_record(record)
        assert "password" not in result
        assert "api_key" not in result
        assert "token" not in result
        assert result["id"] == "test-1"
        assert result["name"] == "Test"

    def test_normalize_record_excludes_volatile_timestamps(self):
        """Runtime timestamps are excluded unless semantic."""
        record = {
            "id": "test-1",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-02T00:00:00+00:00",
            "occurred_at": "2024-01-15T10:00:00+00:00",  # Semantic temporal
            "request_id": "req-123",
        }
        result = _normalize_record(record)
        assert "created_at" not in result
        assert "updated_at" not in result
        assert "request_id" not in result
        assert "occurred_at" in result  # Semantic temporal preserved


class TestComponentFingerprint:
    """Tests for individual component fingerprints."""

    @pytest.mark.asyncio
    async def test_organization_component(
        self,
        pg_db_session: AsyncSession,
    ):
        """Organization component fingerprint is deterministic."""
        org = Organization(
            name="Test Corp",
            slug=f"test-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        org_comp = next((c for c in tenant_fp.components if c.component_name == "organization"), None)
        assert org_comp is not None
        assert org_comp.entity_count >= 1
        assert len(org_comp.fingerprint) == 64  # SHA256 hex digest

    @pytest.mark.asyncio
    async def test_deterministic_repeatability(
        self,
        pg_db_session: AsyncSession,
    ):
        """Same data produces same fingerprint on repeated runs."""
        org = Organization(
            name="Repeat Corp",
            slug=f"repeat-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint == fp2.aggregate_fingerprint
        assert len(fp1.components) == len(fp2.components)
        for c1, c2 in zip(fp1.components, fp2.components):
            assert c1.fingerprint == c2.fingerprint

    @pytest.mark.asyncio
    async def test_irrelevant_ordering_no_change(
        self,
        pg_db_session: AsyncSession,
    ):
        """Different query ordering produces same fingerprint."""
        org = Organization(
            name="Order Corp",
            slug=f"order-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        # Compute multiple times - query order might vary but fingerprint should not
        fingerprints = []
        for _ in range(5):
            fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
            fingerprints.append(fp.aggregate_fingerprint)
        
        # All should be identical
        assert len(set(fingerprints)) == 1

    @pytest.mark.asyncio
    async def test_workforce_component(
        self,
        pg_db_session: AsyncSession,
    ):
        """Workforce component captures departments, teams, roles."""
        org = Organization(
            name="Workforce Corp",
            slug=f"workforce-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        dept = Department(organization_id=org.id, name="Engineering", code="ENG")
        pg_db_session.add(dept)
        await pg_db_session.flush()
        
        team = Team(organization_id=org.id, name="Backend", code="BE", department_id=dept.id)
        pg_db_session.add(team)
        
        role = Role(organization_id=org.id, code="engineer", name="Engineer")
        pg_db_session.add(role)
        
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        workforce_comp = next((c for c in tenant_fp.components if c.component_name == "workforce"), None)
        assert workforce_comp is not None
        assert workforce_comp.entity_count >= 3  # dept + team + role


class TestAggregateFingerprint:
    """Tests for aggregate fingerprint computation."""

    @pytest.mark.asyncio
    async def test_aggregate_changes_with_data(
        self,
        pg_db_session: AsyncSession,
    ):
        """Aggregate fingerprint changes when canonical data changes."""
        org = Organization(
            name="Aggregate Corp",
            slug=f"agg-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Add a decision
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Test Decision",
            state="proposed",
            source_event_id="evt-001",
        )
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint
        # The company_decisions component should show the change
        dec_comp_1 = next((c for c in fp1.components if c.component_name == "company_decisions"), None)
        dec_comp_2 = next((c for c in fp2.components if c.component_name == "company_decisions"), None)
        assert dec_comp_1 is not None and dec_comp_2 is not None
        assert dec_comp_1.fingerprint != dec_comp_2.fingerprint
        assert dec_comp_2.entity_count > dec_comp_1.entity_count

    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self,
        pg_db_session: AsyncSession,
    ):
        """Tenant A changes don't affect Tenant B fingerprint."""
        org_a = Organization(name="Tenant A", slug=f"tenant-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Tenant B", slug=f"tenant-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp_a_before = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_before = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Add decision to tenant A
        decision = CompanyDecision(organization_id=org_a.id, decision_id="DEC-A-001", kind="strategic", title="A's Decision", state="proposed", source_event_id="evt-001")
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp_a_after = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_after = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Tenant A changed
        assert fp_a_before.aggregate_fingerprint != fp_a_after.aggregate_fingerprint
        # Tenant B unchanged
        assert fp_b_before.aggregate_fingerprint == fp_b_after.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_reverse_tenant_isolation(
        self,
        pg_db_session: AsyncSession,
    ):
        """Tenant B changes don't affect Tenant A fingerprint."""
        org_a = Organization(name="Tenant A Rev", slug=f"tenant-a-rev-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Tenant B Rev", slug=f"tenant-b-rev-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp_a_before = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_before = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Add decision to tenant B
        decision = CompanyDecision(organization_id=org_b.id, decision_id="DEC-B-001", kind="strategic", title="B's Decision", state="proposed", source_event_id="evt-002")
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp_a_after = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_after = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Tenant B changed
        assert fp_b_before.aggregate_fingerprint != fp_b_after.aggregate_fingerprint
        # Tenant A unchanged
        assert fp_a_before.aggregate_fingerprint == fp_a_after.aggregate_fingerprint


class TestSemanticChanges:
    """Tests that meaningful canonical changes affect fingerprint."""

    @pytest.mark.asyncio
    async def test_decision_state_change(
        self,
        pg_db_session: AsyncSession,
    ):
        """Decision state transition changes fingerprint."""
        org = Organization(name="Decision Corp", slug=f"dec-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Important Decision",
            state="proposed",
            source_event_id="evt-001",
            event_name="test_event",
        )
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Transition to approved
        decision.state = "approved"
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_authorization_state_change(
        self,
        pg_db_session: AsyncSession,
    ):
        """Authorization approval changes fingerprint."""
        org = Organization(name="Auth Corp", slug=f"auth-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        auth = CompanyAuthorization(
            organization_id=org.id,
            title="Budget Authorization",
            state="requested",
            authorization_type="full",
            scope_type="company",
            fingerprint="test-fp-1",
            valid_from=utcnow(),
        )
        pg_db_session.add(auth)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Approve
        auth.state = "approved"
        auth.approved_by = "user-1"
        auth.approved_at = utcnow()
        auth.fingerprint = "test-fp-2"
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_commitment_fulfillment(
        self,
        pg_db_session: AsyncSession,
    ):
        """Commitment fulfillment changes fingerprint."""
        org = Organization(name="Commit Corp", slug=f"commit-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        auth = CompanyAuthorization(organization_id=org.id, title="Auth", state="approved", fingerprint=uuid.uuid4().hex)
        pg_db_session.add(auth)
        await pg_db_session.flush()
        
        commitment = CompanyCommitment(
            organization_id=org.id,
            title="Deliver Project",
            state="active",
            authorization_id=auth.id,
            commitment_type="unconditional",
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(commitment)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Fulfill commitment
        commitment.state = "fulfilled"
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_action_execution(
        self,
        pg_db_session: AsyncSession,
    ):
        """Action execution changes fingerprint."""
        org = Organization(name="Action Corp", slug=f"action-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        action = CompanyAction(
            organization_id=org.id,
            title="Deploy Feature",
            state="ready",
            action_type="deployment",
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(action)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Execute
        action.state = "in_progress"
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_provenance_change(
        self,
        pg_db_session: AsyncSession,
    ):
        """Provenance reference change affects fingerprint."""
        org = Organization(name="Prov Corp", slug=f"prov-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        decision = CompanyDecision(organization_id=org.id, decision_id="DEC-001", kind="strategic", title="Dec", state="approved", source_event_id=uuid.uuid4().hex)
        pg_db_session.add(decision)
        await pg_db_session.flush()
        
        auth = CompanyAuthorization(
            organization_id=org.id,
            title="Auth",
            state="approved",
            decision_id=decision.id,
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(auth)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Change decision reference
        auth.decision_id = None  # Remove provenance
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_temporal_change(
        self,
        pg_db_session: AsyncSession,
    ):
        """Temporal interval change affects fingerprint."""
        org = Organization(name="Temp Corp", slug=f"temp-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        auth = CompanyAuthorization(
            organization_id=org.id,
            title="Temporal Auth",
            state="approved",
            valid_from=datetime.now(timezone.utc) + timedelta(days=1),
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(auth)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Change temporal bounds
        auth.valid_until = datetime.now(timezone.utc) + timedelta(days=60)
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_epistemic_promotion(
        self,
        pg_db_session: AsyncSession,
    ):
        """Epistemic status promotion affects fingerprint."""
        from app.models.organizational_learning import OrganizationalLearning
        
        org = Organization(name="Epi Corp", slug=f"epi-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        learning = OrganizationalLearning(
            organization_id=org.id,
            kind="pattern",
            title="Test Learning",
            lifecycle="proposed",
            confidence=0.8,
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(learning)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Promote to confirmed
        learning.lifecycle = "confirmed"
        learning.confidence = 0.95
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint

    @pytest.mark.asyncio
    async def test_governance_policy_change(
        self,
        pg_db_session: AsyncSession,
    ):
        """Governance policy change affects fingerprint."""
        org = Organization(name="Gov Corp", slug=f"gov-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        policy = ApprovalPolicy(
            organization_id=org.id,
            name="Test Policy",
            approval_type="decision",
            required_permission="decision:approve",
        )
        pg_db_session.add(policy)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Change policy
        policy.required_permission = "decision:execute"
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint


class TestTemporalFingerprinting:
    """Tests for temporal state preservation."""

    @pytest.mark.asyncio
    async def test_historical_state_preserved(
        self,
        pg_db_session: AsyncSession,
    ):
        """Historical (superseded) state remains in fingerprint."""
        org = Organization(name="History Corp", slug=f"hist-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create original commitment
        auth = CompanyAuthorization(organization_id=org.id, title="Auth", state="approved", fingerprint=uuid.uuid4().hex)
        pg_db_session.add(auth)
        await pg_db_session.flush()
        
        commitment = CompanyCommitment(
            organization_id=org.id,
            title="Original Commitment",
            state="superseded",  # Already superseded
            authorization_id=auth.id,
            commitment_type="unconditional",
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(commitment)
        await pg_db_session.flush()
        
        # Create superseding commitment
        new_commitment = CompanyCommitment(
            organization_id=org.id,
            title="New Commitment",
            state="active",
            authorization_id=auth.id,
            supersedes_id=commitment.id,
            commitment_type="unconditional",
            fingerprint=uuid.uuid4().hex,
        )
        pg_db_session.add(new_commitment)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Both commitments should be reflected
        commit_comp = next((c for c in fp.components if c.component_name == "company_commitments"), None)
        assert commit_comp is not None
        assert commit_comp.entity_count >= 2

    @pytest.mark.asyncio
    async def test_supersession_chain_affects_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Supersession chain changes affect fingerprint."""
        org = Organization(name="Super Corp", slug=f"super-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        auth = CompanyAuthorization(organization_id=org.id, title="Auth", state="approved", fingerprint=uuid.uuid4().hex)
        pg_db_session.add(auth)
        await pg_db_session.flush()
        
        c1 = CompanyCommitment(organization_id=org.id, title="C1", state="superseded", authorization_id=auth.id, commitment_type="unconditional", fingerprint=uuid.uuid4().hex)
        pg_db_session.add(c1)
        await pg_db_session.flush()
        
        c2 = CompanyCommitment(organization_id=org.id, title="C2", state="active", authorization_id=auth.id, supersedes_id=c1.id, commitment_type="unconditional", fingerprint=uuid.uuid4().hex)
        pg_db_session.add(c2)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Add another supersession
        c3 = CompanyCommitment(organization_id=org.id, title="C3", state="active", authorization_id=auth.id, supersedes_id=c2.id, commitment_type="unconditional", fingerprint=uuid.uuid4().hex)
        c2.state = "superseded"
        pg_db_session.add_all([c2, c3])
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint


class TestReleaseCandidateFingerprint:
    """Tests for release candidate fingerprint evidence."""

    @pytest.mark.asyncio
    async def test_create_release_candidate_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Release candidate fingerprint captures all tenants."""
        org_a = Organization(name="RCA", slug=f"rc-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="RCB", slug=f"rc-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        
        # Add some data
        dec = CompanyDecision(organization_id=org_a.id, decision_id="DEC-1", kind="strategic", title="A Dec", state="approved", source_event_id=uuid.uuid4().hex)
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        rc_fp = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id=f"rc-{uuid.uuid4().hex[:8]}",
            application_version="1.0.0",
            schema_revision="head",
            organization_ids=[org_a.id, org_b.id],
        )
        
        assert len(rc_fp.tenants) == 2
        assert rc_fp.application_version == "1.0.0"
        assert rc_fp.schema_revision == "head"
        
        # Each tenant has components
        for tenant in rc_fp.tenants:
            assert len(tenant.components) > 0
            assert tenant.aggregate_fingerprint
            assert tenant.status == FingerprintStatus.COMPUTED

    @pytest.mark.asyncio
    async def test_fingerprint_comparison_match(
        self,
        pg_db_session: AsyncSession,
    ):
        """Identical fingerprints compare as MATCH."""
        org = Organization(name="Compare Corp", slug=f"cmp-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MATCH"

    @pytest.mark.asyncio
    async def test_fingerprint_comparison_mismatch(
        self,
        pg_db_session: AsyncSession,
    ):
        """Different canonical state detected as MISMATCH."""
        org_a = Organization(name="Org A", slug=f"cmp-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Org B", slug=f"cmp-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        
        # Only org_a has a decision
        dec = CompanyDecision(organization_id=org_a.id, decision_id="DEC-1", kind="strategic", title="Decision", state="approved", source_event_id=uuid.uuid4().hex)
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
            organization_ids=[org_a.id],  # Only one org
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MISMATCH"

    @pytest.mark.asyncio
    async def test_component_level_diff(
        self,
        pg_db_session: AsyncSession,
    ):
        """Component-level differences are identified."""
        org = Organization(name="Diff Corp", slug=f"diff-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        # Add decision
        dec = CompanyDecision(organization_id=org.id, decision_id="DEC-NEW", kind="strategic", title="New Decision", state="approved", source_event_id=uuid.uuid4().hex)
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MISMATCH"
        assert len(result["component_differences"]) > 0
        diff = result["component_differences"][0]
        assert diff["component"] == f"{org.id}:company_decisions"


class TestFailureBehavior:
    """Tests for fingerprint failure handling."""

    @pytest.mark.asyncio
    async def test_missing_required_table_blocks(
        self,
        pg_db_session: AsyncSession,
    ):
        """Missing required component blocks fingerprint."""
        org = Organization(name="Block Corp", slug=f"block-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        # Create custom service with non-existent required table
        custom_components = [
            FingerprintComponent(
                name="nonexistent",
                tables=["this_table_does_not_exist_at_all_xyz"],
                required=True,
            ),
        ]
        
        service = CanonicalFingerprintService()
        
        # Override the component list temporarily
        original = CANONICAL_COMPONENTS
        try:
            import app.services.canonical_fingerprint as cf_module
            cf_module.CANONICAL_COMPONENTS = custom_components
            
            tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
            assert tenant_fp.status == FingerprintStatus.BLOCKED
            assert tenant_fp.error is not None
        finally:
            cf_module.CANONICAL_COMPONENTS = original

    @pytest.mark.asyncio
    async def test_secret_not_in_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Secrets are never included in fingerprint."""
        org = Organization(
            name="Secret Corp",
            slug=f"sec-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create connector with secret
        from app.models.canonical_integration import Connector, ConnectorInstance
        connector_def = Connector(
            id=f"test-connector-{uuid.uuid4().hex[:8]}",
            kind="communication",
            provider=f"test-{uuid.uuid4().hex[:8]}",
            display_name="Test Connector",
        )
        pg_db_session.add(connector_def)
        await pg_db_session.flush()
        connector = ConnectorInstance(
            organization_id=org.id,
            connector_id=connector_def.id,
            name="Test Connector",
            config={"api_key": "secret-key-123", "webhook_secret": "webhook-secret"},
        )
        pg_db_session.add(connector)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Verify the fingerprint doesn't contain the secret
        from dataclasses import asdict
        fp_str = str(asdict(tenant_fp))
        assert "secret-key-123" not in fp_str
        assert "webhook-secret" not in fp_str


class TestIntegrationWithPreflight:
    """Tests for integration with ReleaseSafetyPreflight."""

    @pytest.mark.asyncio
    async def test_preflight_includes_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Release preflight produces fingerprint evidence."""
        org = Organization(
            name="PF Fingerprint Corp",
            slug=f"pf-fp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        backup = BackupManifest(
            id=f"bkp-pf-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            backup_kind=BackupKind.PRE_DEPLOYMENT,
            status=BackupStatus.VERIFIED,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            backup_size_bytes=1024 * 1024 * 100,
            checksum_sha256="a" * 64,
        )
        pg_db_session.add(backup)
        
        policy = ApprovalPolicy(
            organization_id=org.id,
            name="Test Policy",
            approval_type="decision",
            required_permission="decision:create",
        )
        pg_db_session.add(policy)
        await pg_db_session.commit()
        
        # Run preflight
        result = await release_safety_preflight.run_preflight(
            db=pg_db_session,
            organization_id=org.id,
            require_backup=True,
            require_dr=True,
        )
        
        assert result.overall_status.value in ("ready", "warning")
        
        # Create fingerprint evidence
        rc_service = ReleaseCandidateFingerprintService()
        rc_fp = await rc_service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id=f"rc-{uuid.uuid4().hex[:8]}",
            application_version="1.0.0",
            schema_revision="head",
            preflight_verdict=result.overall_status.value,
            preflight_timestamp=result.completed_at,
        )
        
        assert len(rc_fp.tenants) >= 1
        assert rc_fp.preflight_verdict == result.overall_status.value


class TestFingerprintAlgorithms:
    """Tests for fingerprint algorithm variants."""

    @pytest.mark.asyncio
    async def test_sha256_64_algorithm(
        self,
        pg_db_session: AsyncSession,
    ):
        """SHA256_64 produces 64-char fingerprints."""
        org = Organization(name="Algo Corp", slug=f"algo-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService(algorithm=FingerprintAlgorithm.SHA256_64)
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert len(tenant_fp.aggregate_fingerprint) == 64
        for comp in tenant_fp.components:
            assert len(comp.fingerprint) == 64
            assert comp.algorithm == FingerprintAlgorithm.SHA256_64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])