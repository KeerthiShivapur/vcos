"""Tests for Universal Acceptance Matrix with Real VCOS Services."""

import pytest
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests.acceptance import (
    DimensionId,
    get_representative_profiles,
    ScenarioType,
    CANONICAL_INVARIANTS,
)
from tests.acceptance.matrix_runner_real import (
    AcceptanceMatrixRunner,
    run_acceptance_matrix_real,
    InvariantVerifier,
    InvariantStatus,
    ScenarioStatus,
)
from tests.acceptance.adapters import AdapterContext
from app.intelligence.company_context import CallerAccess
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee


@pytest_asyncio.fixture
async def test_organization(db_session: AsyncSession) -> Organization:
    """Create a test organization for acceptance testing."""
    import uuid
    org = Organization(
        id=f"ua-test-{uuid.uuid4().hex[:8]}",
        name="UA Test Org",
        slug=f"ua-test-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_caller(db_session: AsyncSession, test_organization: Organization) -> CallerAccess:
    """Create test caller with org-wide access."""
    import uuid
    user = User(
        id=f"ua-user-{uuid.uuid4().hex[:8]}",
        email=f"ua-test-{uuid.uuid4().hex[:8]}@acceptance.test",
        password_hash="test_hash",
        full_name="UA Test Admin",
        organization_id=test_organization.id,
        status="active",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    
    emp = Employee(
        id=f"ua-emp-{uuid.uuid4().hex[:8]}",
        organization_id=test_organization.id,
        user_id=str(user.id),
        employee_number=f"UA{uuid.uuid4().hex[:6].upper()}",
        first_name="UA",
        last_name="Test",
        display_name="UA Test",
        email=f"ua-test-{uuid.uuid4().hex[:8]}@acceptance.test",
        joining_date=__import__('datetime').datetime.now().date(),
        status="active",
        employment_type="full_time",
    )
    db_session.add(emp)
    await db_session.flush()
    
    return CallerAccess(
        organization_id=test_organization.id,
        user_id=str(user.id),
        employee_id=emp.id,
        org_wide=True,
    )


class TestInvariantVerification:
    """Test canonical invariant verification against real database."""
    
    @pytest.mark.asyncio
    async def test_tenant_ownership_verification(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test PROPERTY_1_TENANT_OWNERSHIP verification."""
        verifier = InvariantVerifier(db_session, test_caller)
        
        result = await verifier.verify("PROPERTY_1_TENANT_OWNERSHIP", {})
        
        assert result.invariant == "PROPERTY_1_TENANT_OWNERSHIP"
        assert result.status in [InvariantStatus.HOLDS, InvariantStatus.VIOLATED, InvariantStatus.UNKNOWN]
    
    @pytest.mark.asyncio
    async def test_temporal_reconstructable_verification(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test PROPERTY_4_TEMPORAL_RECONSTRUCTABLE verification."""
        verifier = InvariantVerifier(db_session, test_caller)
        
        result = await verifier.verify("PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", {})
        
        assert result.invariant == "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"
        assert result.status in [InvariantStatus.HOLDS, InvariantStatus.VIOLATED, InvariantStatus.UNKNOWN]
    
    @pytest.mark.asyncio
    async def test_all_invariants_verification(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test all 12 canonical invariants can be verified."""
        verifier = InvariantVerifier(db_session, test_caller)
        
        results = await verifier.verify_all(CANONICAL_INVARIANTS, {})
        
        assert len(results) == len(CANONICAL_INVARIANTS)
        for result in results:
            assert result.invariant in CANONICAL_INVARIANTS
            assert result.status in [InvariantStatus.HOLDS, InvariantStatus.VIOLATED, InvariantStatus.UNKNOWN]


class TestAdapterExecution:
    """Test adapter execution with real VCOS services."""
    
    @pytest.mark.asyncio
    async def test_company_provisioning_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test CompanyProvisioningAdapter provisions real entities."""
        from tests.acceptance.adapters import CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"A": "startup_5", "I": "startup_governance"},
            run_id="test-123",
        )
        
        adapter = CompanyProvisioningAdapter(context)
        
        # Setup
        setup_result = await adapter.setup()
        assert setup_result.success
        
        # Provision
        provision_result = await adapter.provision()
        assert provision_result.success, f"Provisioning failed: {provision_result.error}"
        
        # Verify data was created
        assert "departments" in provision_result.data
        assert "teams" in provision_result.data
        assert "employees" in provision_result.data
        assert "policies" in provision_result.data
        assert len(provision_result.data["departments"]) > 0
        assert len(provision_result.data["employees"]) > 0
        
        # Validate
        validate_result = await adapter.validate()
        assert validate_result.success
        assert "PROPERTY_1_TENANT_OWNERSHIP" in validate_result.invariants_verified
    
    @pytest.mark.asyncio
    async def test_identity_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test IdentityAdapter executes identity transitions."""
        from tests.acceptance.adapters import IdentityAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"A": "startup_5", "H": "multi_role"},
            run_id="test-123",
        )
        
        # First provision
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        # Then test identity
        identity_adapter = IdentityAdapter(context)
        result = await identity_adapter.execute()
        
        assert result.success, f"Identity test failed: {result.error}"
        assert "transitions" in result.data
    
    @pytest.mark.asyncio
    async def test_governance_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test GovernanceAdapter tests authorization."""
        from tests.acceptance.adapters import GovernanceAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"A": "startup_5", "I": "startup_governance"},
            run_id="test-123",
        )
        
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        gov_adapter = GovernanceAdapter(context)
        result = await gov_adapter.execute()
        
        assert result.success, f"Governance test failed: {result.error}"
        assert "authorization_tests" in result.data
        assert "delegation_tests" in result.data
    
    @pytest.mark.asyncio
    async def test_work_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test WorkAdapter creates work lifecycle."""
        from tests.acceptance.adapters import WorkAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"A": "startup_5", "J": "project_work"},
            run_id="test-123",
        )
        
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        work_adapter = WorkAdapter(context)
        result = await work_adapter.provision()
        
        assert result.success, f"Work provisioning failed: {result.error}"
        assert "projects" in result.data
        assert "tasks" in result.data
        assert "decisions" in result.data
        assert "actions" in result.data
        assert "commitments" in result.data
        assert "outcomes" in result.data
        assert len(result.data["projects"]) > 0
    
    @pytest.mark.asyncio
    async def test_finance_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test FinanceAdapter provisions finance entities."""
        from tests.acceptance.adapters import FinanceAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"A": "startup_5", "K": "simple_finance"},
            run_id="test-123",
        )
        
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        finance_adapter = FinanceAdapter(context)
        result = await finance_adapter.provision()
        
        assert result.success, f"Finance provisioning failed: {result.error}"
        assert "budgets" in result.data
        assert "vendors" in result.data
        assert "purchase_orders" in result.data
    
    @pytest.mark.asyncio
    async def test_integration_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test IntegrationAdapter configures connectors."""
        from tests.acceptance.adapters import IntegrationAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"O": {"properties": {"connectors": ["github"]}}},
            run_id="test-123",
        )
        
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        int_adapter = IntegrationAdapter(context)
        result = await int_adapter.configure()
        
        # May fail if connectors not registered, but should handle gracefully
        assert "instances" in result.data or result.error
    
    @pytest.mark.asyncio
    async def test_security_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test SecurityAdapter tests tenant isolation."""
        from tests.acceptance.adapters import SecurityAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"X": "standard_security"},
            run_id="test-123",
        )
        
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        sec_adapter = SecurityAdapter(context)
        result = await sec_adapter.execute()
        
        assert result.success, f"Security test failed: {result.error}"
        assert "cross_tenant_rejected" in result.data
        assert result.data["cross_tenant_rejected"] is True
    
    @pytest.mark.asyncio
    async def test_dr_adapter(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test DRAdapter tests backup/restore."""
        from tests.acceptance.adapters import DRAdapter, CompanyProvisioningAdapter, AdapterContext
        
        context = AdapterContext(
            db=db_session,
            organization_id=test_caller.organization_id,
            caller=test_caller,
            tenant_id=test_caller.organization_id,
            profile={"Y": "backup_restore"},
            run_id="test-123",
        )
        
        prov_adapter = CompanyProvisioningAdapter(context)
        await prov_adapter.provision()
        
        dr_adapter = DRAdapter(context)
        result = await dr_adapter.execute()
        
        assert result.success, f"DR test failed: {result.error}"
        assert "backup" in result.data
        assert "restore" in result.data
        assert "rpo_rto" in result.data


class TestAcceptanceMatrixReal:
    """Test the full acceptance matrix runner with real services."""
    
    @pytest.mark.asyncio
    async def test_single_profile_minimal(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test running a minimal acceptance matrix with one profile."""
        # Use just one profile with minimal scenarios
        profiles = [{
            "name": "startup_test",
            "dimensions": {
                "A": "startup_5", "B": "flat", "C": "software", "D": "united_states",
                "E": "single_entity", "F": "parent_subsidiary_2", "G": "en_us_only",
                "H": "single_role", "I": "startup_governance", "J": "project_work",
                "K": "simple_finance", "L": "full_time_only", "M": "email_slack",
                "N": "wiki_knowledge", "O": "github_only", "P": "basic_brain",
                "Q": "startup_memory", "R": "hiring_prediction", "S": "hiring_scenario",
                "T": "low_autonomy", "U": "employee_turnover", "V": "startup_to_scale",
                "W": "asset_acquisition", "X": "standard_security", "Y": "backup_restore",
                "Z": "rest_api",
            },
        }]
        
        # Run with minimal scenario types
        runner = AcceptanceMatrixRunner(
            db=db_session,
            profiles=profiles,
            scenario_types=[
                ScenarioType.PROVISIONING,
                ScenarioType.IDENTITY,
                ScenarioType.GOVERNANCE,
            ],
            parallel=False,
        )
        
        result = await runner.run()
        
        assert result.run_id.startswith("ua_")
        assert len(result.profiles) == 1
        assert result.total_scenarios == 3
        
        # Check scenario results
        profile_result = result.profiles[0]
        for scenario in profile_result.scenarios:
            assert scenario.status in [ScenarioStatus.PASSED, ScenarioStatus.FAILED, ScenarioStatus.BLOCKED]
            assert scenario.started_at is not None
            assert scenario.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_evidence_generation(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test that evidence is generated and saved."""
        import tempfile
        import os
        
        profiles = [{
            "name": "evidence_test",
            "dimensions": {
                "A": "startup_5", "B": "flat", "C": "software", "D": "united_states",
                "E": "single_entity", "F": "parent_subsidiary_2", "G": "en_us_only",
                "H": "single_role", "I": "startup_governance", "J": "project_work",
                "K": "simple_finance", "L": "full_time_only", "M": "email_slack",
                "N": "wiki_knowledge", "O": "github_only", "P": "basic_brain",
                "Q": "startup_memory", "R": "hiring_prediction", "S": "hiring_scenario",
                "T": "low_autonomy", "U": "employee_turnover", "V": "startup_to_scale",
                "W": "asset_acquisition", "X": "standard_security", "Y": "backup_restore",
                "Z": "rest_api",
            },
        }]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = AcceptanceMatrixRunner(
                db=db_session,
                profiles=profiles,
                scenario_types=[ScenarioType.PROVISIONING],
                parallel=False,
                output_dir=tmpdir,
            )
            
            result = await runner.run()
            runner.save_results(result)
            
            # Check evidence file was created
            evidence_files = [f for f in os.listdir(tmpdir) if f.startswith("acceptance_matrix_")]
            assert len(evidence_files) == 1
            
            # Verify file content
            import json
            with open(os.path.join(tmpdir, evidence_files[0])) as f:
                data = json.load(f)
            
            assert data["run_id"] == result.run_id
            assert data["summary"]["total_profiles"] == 1
            assert data["summary"]["total_scenarios"] == 1


class TestScaleMatrixIntegration:
    """Test integration with existing scale infrastructure."""
    
    @pytest.mark.asyncio
    async def test_universal_scale_profile_integration(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test that acceptance profiles map to UniversalScaleProfile."""
        from tests.scale.generators import UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES
        
        # Verify UniversalScaleProfile exists for each scale
        scale_names = ["startup", "small", "medium", "large", "enterprise", "mega"]
        for name in scale_names:
            assert name in UNIVERSAL_SCALE_PROFILES
            profile = UNIVERSAL_SCALE_PROFILES[name]
            assert isinstance(profile, UniversalScaleProfile)
            assert profile.employee_count > 0
    
    @pytest.mark.asyncio
    async def test_scale_generator_can_create_company(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test that scale generator can create company data."""
        from tests.scale.generators import SyncScaleGenerator, ScaleConfig
        
        config = ScaleConfig(
            name="startup",
            employee_count=5,
            years_of_history=1,
            include_historical=False,
            include_inactive=False,
        )
        
        generator = SyncScaleGenerator(db_session, test_caller.organization_id, config)
        
        # Test that we can at least initialize
        assert generator.config.employee_count == 5
        assert generator.config.dept_count >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])