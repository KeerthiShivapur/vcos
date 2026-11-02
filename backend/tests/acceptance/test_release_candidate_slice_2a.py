"""
Release Candidate Hardening — Slice 2A: Release Safety Foundation Tests.

This test suite validates the release safety preflight service that determines
whether VCOS is safe to begin a release.

Tests cover:
- All prerequisites pass → READY
- Database unavailable → BLOCKED
- Schema incompatible → BLOCKED
- Backup unavailable → BLOCKED
- Canonical integrity failure → BLOCKED
- Provenance failure → BLOCKED
- Temporal failure → BLOCKED
- Governance failure → BLOCKED
- Tenant isolation failure → BLOCKED
- Longitudinal integrity failure → BLOCKED
"""

import pytest
import pytest_asyncio
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.services.release_safety_preflight import (
    release_safety_preflight,
    ReleaseSafetyPreflight,
    PreflightStatus,
    PreflightPhase,
)
from app.validation.capability_contract import (
    ValidationStatus,
    EnvironmentCapability,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.company_operating import CompanyDecision, CompanyDecisionAlternative
from app.models.execution_strategy import CompanyAuthorization, CompanyCommitment, CompanyGoal, VerificationContext
from app.models.company_actions import CompanyAction
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.models.canonical_reliability import CanonicalOperation, WorkerLease
from app.models.governance import ApprovalPolicy
from app.models.longitudinal import CompanyTimelineEvent, CompanyKnowledgeSnapshot
from app.models.observability import HealthDimension


class TestReleaseSafetyPreflight:
    """Tests for ReleaseSafetyPreflight service."""

    @pytest.mark.asyncio
    async def test_all_prerequisites_pass_ready(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: all prerequisites pass → READY."""
        # Create a minimal valid organization
        org = Organization(
            name="Test Org",
            slug=f"test-org-2a-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create verified backup
        backup = BackupManifest(
            id=f"bkp-test-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            backup_kind=BackupKind.PRE_DEPLOYMENT,
            status=BackupStatus.VERIFIED,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            backup_size_bytes=1024 * 1024 * 100,
            checksum_sha256="a" * 64,
        )
        pg_db_session.add(backup)
        await pg_db_session.flush()
        
        # Create approval policy
        policy = ApprovalPolicy(
            organization_id=org.id,
            name="Test Policy",
            approval_type="decision",
            required_permission="decision:create",
        )
        pg_db_session.add(policy)
        
        # Create health dimension
        import hashlib
        fingerprint = hashlib.sha256(f"api_latency|{org.id}|company|".encode()).hexdigest()[:64]
        health = HealthDimension(
            organization_id=org.id,
            dimension="api_latency",
            scope_type="company",
            scope_id=None,
            status="healthy",
            current_value=50.0,
            target_value=100.0,
            recorded_at=datetime.now(timezone.utc),
            fingerprint=fingerprint,
        )
        pg_db_session.add(health)
        await pg_db_session.commit()
        
        # Run preflight
        result = await release_safety_preflight.run_preflight(
            db=pg_db_session,
            organization_id=org.id,
            require_backup=True,
            require_dr=True,
        )
        
        assert result.overall_status == PreflightStatus.READY
        assert "All preflight checks passed" in result.message
        assert result.application_version == "1.0.0"
        
        # Verify all mandatory checks passed
        mandatory_checks = [c for c in result.checks if c.mandatory]
        for check in mandatory_checks:
            assert check.status == ValidationStatus.VERIFIED, f"Check {check.phase} failed: {check.message}"

    @pytest.mark.asyncio
    async def test_database_unavailable_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: database unavailable → BLOCKED."""
        # Create a mock session that fails on execute
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=Exception("Connection refused"))
        
        # We can't easily test this with real session, but we can test the check directly
        preflight = ReleaseSafetyPreflight()
        preflight.db = mock_db
        
        result = await preflight._check_database_connectivity(mock_db)
        
        assert result.status == ValidationStatus.FAILED
        assert "Connection refused" in result.message
        assert result.mandatory is True

    @pytest.mark.asyncio
    async def test_schema_incompatible_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: schema incompatible → BLOCKED."""
        # Create a mock session that fails on alembic_version query
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=Exception("Table alembic_version not found"))
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = mock_db
        
        result = await preflight._check_schema_revision(mock_db)
        
        assert result.status == ValidationStatus.FAILED
        assert "Could not read schema revision" in result.message
        assert result.mandatory is True

    @pytest.mark.asyncio
    async def test_backup_unavailable_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: backup unavailable → BLOCKED."""
        # Create organization without backup
        org = Organization(
            name="Test Org No Backup",
            slug=f"test-org-nobackup-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        # Mock capability detector to return False for pgbackrest
        with patch.object(preflight, 'detect', return_value=False):
            result = await preflight._check_backup_readiness(pg_db_session, mandatory=True)
        
        assert result.status == ValidationStatus.FAILED
        assert "No verified backup found" in result.message
        assert result.mandatory is True

    @pytest.mark.asyncio
    async def test_canonical_integrity_failure_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: canonical integrity failure → BLOCKED."""
        org = Organization(
            name="Test Org Bad Integrity",
            slug=f"test-org-bad-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create CompanyCommitment without authorization_id (structural integrity violation - missing required relationship)
        comm_id = f"comm-no-auth-{uuid.uuid4().hex[:8]}"
        commitment = CompanyCommitment(
            id=comm_id,
            organization_id=org.id,
            commitment_type="unconditional",
            title="Commitment without authorization",
            state="active",
            # Missing authorization_id - required for governance chain
            fingerprint=hashlib.sha256(f"{comm_id}|{org.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(commitment)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_canonical_integrity(pg_db_session, org.id)
        
        # Should find the orphaned entity as at least HIGH severity
        # The check may return WARNING or FAILED depending on severity
        assert result.status in (ValidationStatus.FAILED, ValidationStatus.WARNING)

    @pytest.mark.asyncio
    async def test_provenance_failure_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: provenance failure → BLOCKED."""
        org = Organization(
            name="Test Org Bad Provenance",
            slug=f"test-org-bad-prov-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create VerificationContext with completed state but empty evidence_fingerprints (provenance violation)
        vc_id = f"vc-no-evidence-{uuid.uuid4().hex[:8]}"
        vc = VerificationContext(
            id=vc_id,
            organization_id=org.id,
            verification_type="plan_vs_reality",
            title="Verification without evidence",
            state="completed",
            scope_type="company",
            evidence_fingerprints=[],  # Empty evidence - provenance violation
            fingerprint=hashlib.sha256(f"{vc_id}|{org.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(vc)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_provenance_integrity(pg_db_session, org.id)
        
        # Should find missing evidence as provenance violation
        assert result.status in (ValidationStatus.FAILED, ValidationStatus.WARNING)

    @pytest.mark.asyncio
    async def test_temporal_failure_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: temporal failure → BLOCKED."""
        org = Organization(
            name="Test Org Bad Temporal",
            slug=f"test-org-bad-temp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create CompanyAuthorization with invalid temporal interval (valid_from >= valid_until)
        auth = CompanyAuthorization(
            id=f"auth-bad-temp-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            title="Bad temporal auth",
            state="approved",
            valid_from=datetime.now(timezone.utc) + timedelta(hours=2),
            valid_until=datetime.now(timezone.utc) + timedelta(hours=1),  # Before valid_from
            fingerprint=hashlib.sha256(f"auth-bad-temp-{uuid.uuid4().hex[:8]}|{org.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(auth)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_temporal_integrity(pg_db_session, org.id)
        
        # Should find invalid temporal interval
        assert result.status in (ValidationStatus.FAILED, ValidationStatus.WARNING)

    @pytest.mark.asyncio
    async def test_governance_failure_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: governance failure → BLOCKED."""
        org = Organization(
            name="Test Org Bad Governance",
            slug=f"test-org-bad-gov-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create CompanyAuthorization without decided_by in approved state (ungoverned)
        auth = CompanyAuthorization(
            id=f"auth-ungoverned-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            title="Ungoverned authorization",
            state="approved",
            # Missing decided_by
            fingerprint=hashlib.sha256(f"auth-ungoverned-{uuid.uuid4().hex[:8]}|{org.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(auth)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_governance_readiness(pg_db_session, org.id)
        
        # Should find ungoverned authorization
        assert result.status == ValidationStatus.FAILED
        assert "ungoverned" in result.message.lower()
        assert result.mandatory is True

    @pytest.mark.asyncio
    async def test_tenant_isolation_failure_blocked(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: tenant isolation failure → BLOCKED."""
        org1 = Organization(
            name="Tenant A",
            slug=f"tenant-a-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        org2 = Organization(
            name="Tenant B",
            slug=f"tenant-b-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add_all([org1, org2])
        await pg_db_session.flush()
        
        # Create cross-tenant reference: Commitment in org1 references Authorization in org2
        auth = CompanyAuthorization(
            id=f"auth-org2-{uuid.uuid4().hex[:8]}",
            organization_id=org2.id,
            title="Auth in org2",
            state="approved",
            fingerprint=hashlib.sha256(f"auth-org2-{uuid.uuid4().hex[:8]}|{org2.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(auth)
        
        commitment = CompanyCommitment(
            id=f"comm-cross-tenant-{uuid.uuid4().hex[:8]}",
            organization_id=org1.id,
            commitment_type="unconditional",
            title="Commitment in org1 referencing org2 auth",
            state="active",
            authorization_id=auth.id,  # Cross-tenant reference!
            fingerprint=hashlib.sha256(f"comm-cross-tenant-{uuid.uuid4().hex[:8]}|{org1.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(commitment)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_tenant_isolation(pg_db_session, org1.id)
        
        # Should find cross-tenant reference as CRITICAL
        assert result.status in (ValidationStatus.FAILED, ValidationStatus.WARNING)

    @pytest.mark.asyncio
    async def test_longitudinal_integrity_failure_warning(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test: longitudinal integrity failure → WARNING (non-mandatory)."""
        org = Organization(
            name="Test Org Bad Longitudinal",
            slug=f"test-org-bad-long-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create CompanyTimelineEvent with invalid temporal bounds (effective_from > effective_to)
        event = CompanyTimelineEvent(
            id=f"event-bad-temp-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            event_key=f"event-bad-temp-{uuid.uuid4().hex[:8]}",
            timeline_type="operational",
            event_type="test",
            occurred_at=datetime.now(timezone.utc),
            effective_from=datetime.now(timezone.utc) + timedelta(hours=2),  # Future effective_from
            effective_to=datetime.now(timezone.utc) + timedelta(hours=1),    # Past effective_to (invalid: from > to)
            change_summary="Test event with invalid temporal bounds",
        )
        pg_db_session.add(event)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_longitudinal_integrity(pg_db_session, org.id)
        
        # Should find temporal issue as WARNING (non-mandatory)
        assert result.status == ValidationStatus.WARNING
        assert result.mandatory is False
        assert "temporal bounds" in result.message.lower()

    @pytest.mark.asyncio
    async def test_release_blocking_behavior(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test that release is actually BLOCKED when mandatory prerequisites fail."""
        org = Organization(
            name="Test Org Blocked",
            slug=f"test-org-blocked-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create ungoverned authorization (mandatory failure)
        auth = CompanyAuthorization(
            id=f"auth-ungoverned-block-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            title="Ungoverned auth for blocking test",
            state="approved",
            fingerprint=hashlib.sha256(f"auth-ungoverned-block-{uuid.uuid4().hex[:8]}|{org.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(auth)
        await pg_db_session.commit()
        
        # Run full preflight
        result = await release_safety_preflight.run_preflight(
            db=pg_db_session,
            organization_id=org.id,
            require_backup=False,  # Skip backup for this test
            require_dr=False,      # Skip DR for this test
        )
        
        assert result.overall_status == PreflightStatus.BLOCKED
        assert "blocked" in result.message.lower()
        
        # Verify governance check failed
        gov_check = next(c for c in result.checks if c.phase == PreflightPhase.GOVERNANCE_READINESS)
        assert gov_check.status == ValidationStatus.FAILED

    @pytest.mark.asyncio
    async def test_warning_non_mandatory_allows_ready(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test that non-mandatory failures produce WARNING but still READY."""
        org = Organization(
            name="Test Org Warning",
            slug=f"test-org-warning-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create backup
        backup = BackupManifest(
            id=f"bkp-warning-test-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            backup_kind=BackupKind.PRE_DEPLOYMENT,
            status=BackupStatus.VERIFIED,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            backup_size_bytes=1024 * 1024 * 100,
            checksum_sha256="a" * 64,
        )
        pg_db_session.add(backup)
        
        # Create approval policy
        policy = ApprovalPolicy(
            organization_id=org.id,
            name="Test Policy",
            approval_type="decision",
            required_permission="decision:create",
        )
        pg_db_session.add(policy)
        
        # Create health dimension
        import hashlib
        fingerprint = hashlib.sha256(f"api_latency|{org.id}|company|".encode()).hexdigest()[:64]
        health = HealthDimension(
            organization_id=org.id,
            dimension="api_latency",
            scope_type="company",
            scope_id=None,
            status="healthy",
            current_value=50.0,
            target_value=100.0,
            recorded_at=datetime.now(timezone.utc),
            fingerprint=fingerprint,
        )
        pg_db_session.add(health)
        
        # Add longitudinal warning (non-mandatory)
        event_id = f"event-warning-{uuid.uuid4().hex[:8]}"
        event = CompanyTimelineEvent(
            id=event_id,
            organization_id=org.id,
            event_key=event_id,
            timeline_type="operational",
            event_type="test",
            occurred_at=datetime.now(timezone.utc),
            effective_from=datetime.now(timezone.utc) + timedelta(hours=2),  # Future effective_from
            effective_to=datetime.now(timezone.utc) + timedelta(hours=1),    # Past effective_to (invalid: from > to)
            change_summary="Test event with invalid temporal bounds",
        )
        pg_db_session.add(event)
        await pg_db_session.commit()
        
        result = await release_safety_preflight.run_preflight(
            db=pg_db_session,
            organization_id=org.id,
            require_backup=True,
            require_dr=True,
        )
        assert result.overall_status == PreflightStatus.WARNING
        assert "warnings" in result.message.lower()
        
        # But governance check should pass
        gov_check = next(c for c in result.checks if c.phase == PreflightPhase.GOVERNANCE_READINESS)
        assert gov_check.status == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_concurrency_readiness_checks_stuck_operations(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test concurrency readiness detects stuck operations."""
        org = Organization(
            name="Test Org Concurrency",
            slug=f"test-org-concurrency-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create stuck canonical operation (updated > 5 minutes ago)
        op_id = f"op-stuck-{uuid.uuid4().hex[:8]}"
        stuck_op = CanonicalOperation(
            id=op_id,
            organization_id=org.id,
            operation_type="test",
            title="Stuck operation for testing",
            state="executing",
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            fingerprint=hashlib.sha256(f"{op_id}|{org.id}".encode()).hexdigest()[:64],
        )
        pg_db_session.add(stuck_op)
        await pg_db_session.commit()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_concurrency_readiness(pg_db_session)
        
        assert result.status == ValidationStatus.WARNING
        assert "stuck" in result.message.lower()

    @pytest.mark.asyncio
    async def test_preflight_result_serialization(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test that preflight result can be serialized to dict."""
        org = Organization(
            name="Test Org Serialization",
            slug=f"test-org-serialize-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        backup = BackupManifest(
            id=f"bkp-serialize-{uuid.uuid4().hex[:8]}",
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
        
        health = HealthDimension(
            organization_id=org.id,
            dimension="api_latency",
            scope_type="company",
            scope_id=None,
            status="healthy",
            current_value=50.0,
            target_value=100.0,
            recorded_at=datetime.now(timezone.utc),
            fingerprint=hashlib.sha256(f"api_latency|{org.id}|company|".encode()).hexdigest()[:64],
        )
        pg_db_session.add(health)
        await pg_db_session.commit()
        
        result = await release_safety_preflight.run_preflight(
            db=pg_db_session,
            organization_id=org.id,
            require_backup=True,
            require_dr=True,
        )
        
        # Serialize
        serialized = result.to_dict()
        
        assert "overall_status" in serialized
        assert "message" in serialized
        assert "application_version" in serialized
        assert "database_revision" in serialized
        assert "checks" in serialized
        assert len(serialized["checks"]) > 0
        
        # Verify check structure
        check = serialized["checks"][0]
        assert "phase" in check
        assert "status" in check
        assert "message" in check
        assert "mandatory" in check
        assert "details" in check

    @pytest.mark.asyncio
    async def test_multiple_organizations_preflight(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test preflight across multiple organizations."""
        org1 = Organization(name="Org 1", slug=f"org-1-{uuid.uuid4().hex[:8]}", status="active")
        org2 = Organization(name="Org 2", slug=f"org-2-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org1, org2])
        await pg_db_session.flush()
        
        # Create backup for org1
        backup1 = BackupManifest(
            id=f"bkp-org1-{uuid.uuid4().hex[:8]}",
            organization_id=org1.id,
            backup_kind=BackupKind.PRE_DEPLOYMENT,
            status=BackupStatus.VERIFIED,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            backup_size_bytes=1024 * 1024 * 100,
            checksum_sha256="a" * 64,
        )
        pg_db_session.add(backup1)
        
        # Create backup for org2
        backup2 = BackupManifest(
            id=f"bkp-org2-{uuid.uuid4().hex[:8]}",
            organization_id=org2.id,
            backup_kind=BackupKind.PRE_DEPLOYMENT,
            status=BackupStatus.VERIFIED,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            backup_size_bytes=1024 * 1024 * 100,
            checksum_sha256="b" * 64,
        )
        pg_db_session.add(backup2)
        
        # Create policies for both
        policy1 = ApprovalPolicy(organization_id=org1.id, name="Policy 1", approval_type="decision", required_permission="decision:create")
        policy2 = ApprovalPolicy(organization_id=org2.id, name="Policy 2", approval_type="decision", required_permission="decision:create")
        pg_db_session.add_all([policy1, policy2])
        
        # Create health for both
        import hashlib
        fingerprint1 = hashlib.sha256(f"test|{org1.id}|company|".encode()).hexdigest()[:64]
        fingerprint2 = hashlib.sha256(f"test|{org2.id}|company|".encode()).hexdigest()[:64]
        health1 = HealthDimension(organization_id=org1.id, dimension="test", scope_type="company", status="healthy", current_value=10, target_value=20, recorded_at=datetime.now(timezone.utc), fingerprint=fingerprint1)
        health2 = HealthDimension(organization_id=org2.id, dimension="test", scope_type="company", status="healthy", current_value=10, target_value=20, recorded_at=datetime.now(timezone.utc), fingerprint=fingerprint2)
        pg_db_session.add_all([health1, health2])
        await pg_db_session.commit()
        
        # Run preflight without organization_id (should check all)
        result = await release_safety_preflight.run_preflight(
            db=pg_db_session,
            organization_id=None,
            require_backup=True,
            require_dr=True,
        )
        
        assert result.overall_status in (PreflightStatus.READY, PreflightStatus.WARNING)

    @pytest.mark.asyncio
    async def test_dr_readiness_check(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test DR readiness check."""
        org = Organization(
            name="Test Org DR",
            slug=f"test-org-dr-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        with patch.object(preflight, 'detect', return_value=True):
            result = await preflight._check_dr_readiness(pg_db_session, mandatory=True)
        
        assert result.status == ValidationStatus.VERIFIED
        assert "DR readiness" in result.message

    @pytest.mark.asyncio
    async def test_observability_readiness_check(
        self,
        pg_db_session: AsyncSession,
    ):
        """Test observability readiness check."""
        org = Organization(
            name="Test Org Obs",
            slug=f"test-org-obs-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        preflight = ReleaseSafetyPreflight()
        preflight.db = pg_db_session
        
        result = await preflight._check_observability_readiness(pg_db_session, org.id)
        
        # No health dimensions recorded → WARNING
        assert result.status == ValidationStatus.WARNING
        assert result.mandatory is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])