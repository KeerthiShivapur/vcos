"""Universal Acceptance Matrix - Integration Tests.

Tests the complete Universal Acceptance Matrix against real VCOS implementation.
"""

import pytest
import pytest_asyncio
import asyncio
import uuid
import json
import tempfile
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.validation.universal_acceptance import (
    UniversalAcceptanceMatrix,
    UniversalCompanyProfile,
    UniversalAcceptanceCase,
    AcceptanceDimension,
    AcceptanceResult,
    run_universal_acceptance_matrix,
    UniversalAcceptanceReport,
)
from tests.acceptance.dimensions import DimensionId
from app.validation.capability_contract import ValidationStatus
from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder


@pytest.fixture
async def acceptance_matrix(db_session: AsyncSession) -> UniversalAcceptanceMatrix:
    """Create acceptance matrix with database session."""
    matrix = UniversalAcceptanceMatrix(db_session)
    return matrix


@pytest.fixture
def startup_profile() -> dict:
    """Get the startup_5 profile."""
    from tests.acceptance.dimensions import get_representative_profiles
    profiles = get_representative_profiles()
    builder = CompanyProfileBuilder()
    profile = builder.build_representative("startup_software_us")
    return {"profile_id": "startup_5", "profile": profile, "name": "Startup (5 employees)"}


@pytest.fixture
def small_company_profile() -> dict:
    """Get the small_50 profile."""
    from tests.acceptance.dimensions import get_representative_profiles
    profiles = get_representative_profiles()
    builder = CompanyProfileBuilder()
    profile = builder.build_representative("small_manufacturing_eu")
    return {"profile_id": "small_50", "profile": profile, "name": "Small Company (50 employees)"}


@pytest.fixture
def medium_company_profile() -> dict:
    """Get the medium_500 profile."""
    from tests.acceptance.dimensions import get_representative_profiles
    profiles = get_representative_profiles()
    builder = CompanyProfileBuilder()
    profile = builder.build_representative("medium_healthcare_us")
    return {"profile_id": "medium_500", "profile": profile, "name": "Medium Company (500 employees)"}


@pytest.fixture
def large_company_profile() -> dict:
    """Get the large_5k profile."""
    from tests.acceptance.dimensions import get_representative_profiles
    profiles = get_representative_profiles()
    builder = CompanyProfileBuilder()
    profile = builder.build_representative("large_financial_global")
    return {"profile_id": "large_5k", "profile": profile, "name": "Large Company (5,000 employees)"}


@pytest.fixture
def enterprise_profile() -> dict:
    """Get the enterprise_50k profile."""
    from tests.acceptance.dimensions import get_representative_profiles
    profiles = get_representative_profiles()
    builder = CompanyProfileBuilder()
    profile = builder.build_representative("enterprise_multinational")
    return {"profile_id": "enterprise_50k", "profile": profile, "name": "Enterprise (50,000 employees)"}


class TestUniversalAcceptanceMatrixEngine:
    """Test the Universal Acceptance Matrix Engine."""

    @pytest.mark.asyncio
    async def test_matrix_engine_creation(self, acceptance_matrix: UniversalAcceptanceMatrix):
        """Test that the matrix engine can be created."""
        assert acceptance_matrix is not None
        assert len(acceptance_matrix.profiles) == 6
        assert len(acceptance_matrix.cases) > 0

    @pytest.mark.asyncio
    async def test_six_profiles_exist(self, acceptance_matrix: UniversalAcceptanceMatrix):
        """Verify all 6 universal profiles exist."""
        expected_profiles = ["startup_5", "small_50", "medium_500", "large_5k", "enterprise_50k", "mega_500k"]
        
        for profile_id in expected_profiles:
            assert profile_id in acceptance_matrix.profiles, f"Missing profile: {profile_id}"
            profile = acceptance_matrix.profiles[profile_id]
            assert profile.profile_id == profile_id
            assert profile.employee_count > 0
            assert profile.scale_tier in ["startup_5", "small_50", "medium_500", "large_5k", "enterprise_50k", "mega_500k"]

    @pytest.mark.asyncio
    async def test_cases_generated_for_all_dimensions(self, acceptance_matrix: UniversalAcceptanceMatrix):
        """Verify cases generated for all 25 dimensions."""
        dimensions_covered = set()
        for case in acceptance_matrix.cases:
            dimensions_covered.add(case.dimension)
        
        # Should have cases for all 25 dimensions (minus any that are not applicable)
        assert len(dimensions_covered) >= 20, f"Only {len(dimensions_covered)} dimensions covered"
        
        # Check mandatory dimensions are covered
        from app.validation.universal_acceptance import AcceptanceDimension
        mandatory = {
            AcceptanceDimension.CANONICAL_BOUNDARY,
            AcceptanceDimension.TENANT_ISOLATION,
            AcceptanceDimension.CONCURRENCY_FAILURE_TIME,
            AcceptanceDimension.SCALE_MATRIX,
            AcceptanceDimension.EXTRAORDINARY_CAPABILITIES,
        }
        for dim in mandatory:
            assert dim in dimensions_covered, f"Mandatory dimension {dim} not covered"


class TestUniversalAcceptanceCaseExecution:
    """Test execution of individual acceptance cases."""

    @pytest.mark.asyncio
    async def test_universal_org_types_case(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test universal organization types case."""
        case = None
        for case in acceptance_matrix.cases:
            if case.dimension.value == "universal_org_types" and case.profile.profile_id == "startup_5":
                case = case
                break
        
        assert case is not None, "Case not found"
        
        result = await acceptance_matrix._run_case(case)
        
        assert result.result in [AcceptanceResult.PASS, AcceptanceResult.WARNING, AcceptanceResult.INCONCLUSIVE]
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_org_topology_case(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test organization topology case."""
        case = None
        for case in acceptance_matrix.cases:
            if case.dimension.value == "org_topology" and case.profile.profile_id == "startup_5":
                case = case
                break
        
        assert case is not None, "Case not found"
        
        result = await acceptance_matrix._run_case(case)
        
        assert result.result in [AcceptanceResult.PASS, AcceptanceResult.WARNING, AcceptanceResult.INCONCLUSIVE]

    @pytest.mark.asyncio
    async def test_scale_matrix_case(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test scale matrix case."""
        case = None
        for case in acceptance_matrix.cases:
            if case.dimension.value == "scale_matrix" and case.profile.profile_id == "startup_5":
                case = case
                break
        
        assert case is not None, "Case not found"
        
        result = await acceptance_matrix._run_case(case)
        
        assert result.result in [AcceptanceResult.PASS, AcceptanceResult.WARNING, AcceptanceResult.INCONCLUSIVE]


class TestDimensionSpecificVerification:
    """Test dimension-specific verification methods."""

    @pytest.mark.asyncio
    async def test_org_topology_verification(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test organization topology verification."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        from app.validation.universal_acceptance import UniversalCompanyProfile
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.topology_mutation_and_canonical_verification(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_tenant_isolation_verification(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test tenant isolation verification."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.tenant_isolation_and_canonical_verification(profile_obj)
        
        assert result["status"] in [ValidationStatus.VERIFIED, ValidationStatus.NOT_APPLICABLE]

    @pytest.mark.asyncio
    async def test_localization_verification(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test localization verification."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.localization_rendering_and_canonical_verification(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_accessibility_audit(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test accessibility audit."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.wcag_2_1_aa_audit(profile_obj)
        
        assert result["status"] in [ValidationStatus.VERIFIED, ValidationStatus.WARNING, ValidationStatus.NOT_APPLICABLE]

    @pytest.mark.asyncio
    async def test_portability_verification(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test portability verification."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.canonical_export_and_reimport(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_interoperability_verification(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test interoperability verification."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.protocol_semantics_verification(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_api_governance_test(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test API governance and extensibility."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.api_governance_and_extensibility_test(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_workflow_extensibility_test(self, acceptance_matrix: UniversalAcceptanceMatrix, startup_profile: dict):
        """Test workflow extensibility."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="startup_5",
            name="Startup (5 employees)",
            employee_count=5,
            topology=profile[DimensionId.B_ORG_STRUCTURE].id,
            industry=profile[DimensionId.C_INDUSTRY].id,
            geography=profile[DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=profile[DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = await acceptance_matrix.custom_workflow_composition_test(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_industry_universality(self, acceptance_matrix: UniversalAcceptanceMatrix, small_company_profile: dict):
        """Test industry universality."""
        from app.validation.universal_acceptance import UniversalCompanyProfile
        from tests.acceptance.test_acceptance_matrix import CompanyProfileBuilder
        
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("small_manufacturing_eu")
        
        profile_obj = UniversalCompanyProfile(
            profile_id="small_50",
            name="Small Company (50 employees)",
            employee_count=50,
            topology=small_company_profile["profile"][DimensionId.B_ORG_STRUCTURE].id,
            industry=small_company_profile["profile"][DimensionId.C_INDUSTRY].id,
            geography=small_company_profile["profile"][DimensionId.D_GEOGRAPHY].id,
            multi_company=False,
            localization=small_company_profile["profile"][DimensionId.G_LOCALIZATION].id,
            accessibility="standard",
            scale_tier="small_50",
        )
        
        result = await acceptance_matrix.industry_specific_workflow_verification(profile_obj)
        
        assert result["status"] == ValidationStatus.VERIFIED


class TestFullMatrixExecution:
    """Test full matrix execution."""

    @pytest.mark.asyncio
    async def test_full_matrix_run(self, db_session: AsyncSession):
        """Test running the full universal acceptance matrix."""
        matrix = UniversalAcceptanceMatrix(db_session)
        
        report = await matrix.run_all(db_session)
        
        assert report.total_cases > 0
        assert report.run_id.startswith("ua_")
        assert report.started_at is not None
        assert report.completed_at is not None
        assert report.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_report_generation(self, db_session: AsyncSession):
        """Test report generation and serialization."""
        matrix = UniversalAcceptanceMatrix(db_session)
        
        report = await matrix.run_all(db_session)
        
        # Test serialization
        json_str = report.to_json()
        assert "run_id" in json_str
        assert "total_cases" in json_str
        assert "pass_rate" in json_str
        
        # Test file saving
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = report.save(tmpdir)
            assert filepath.exists()
            
            # Verify file content
            with open(filepath) as f:
                data = json.load(f)
                assert data["run_id"] == report.run_id
                assert data["total_cases"] == report.total_cases

    @pytest.mark.asyncio
    async def test_profile_results_tracking(self, db_session: AsyncSession):
        """Test that profile results are tracked correctly."""
        matrix = UniversalAcceptanceMatrix(db_session)
        
        report = await matrix.run_all(db_session)
        
        # Check profile results tracking
        for profile_id, results in report.profile_results.items():
            assert "passed" in results
            assert "failed" in results
            assert "blocked" in results
            assert "inconclusive" in results
            assert sum(results.values()) > 0  # At least some results


class TestUniversalAcceptanceContract:
    """Test the Universal Acceptance Contract."""

    def test_contract_creation(self):
        """Test contract creation."""
        from app.validation.universal_acceptance import UniversalAcceptanceContract
        
        contract = UniversalAcceptanceContract()
        
        assert len(contract.dimensions) == 25
        assert len(contract.mandatory_dimensions) > 0

    def test_dimension_requirements(self):
        """Test dimension requirements retrieval."""
        from app.validation.universal_acceptance import UniversalAcceptanceContract
        
        contract = UniversalAcceptanceContract()
        
        # Test a few dimensions
        req = contract.get_dimension_requirements(AcceptanceDimension.UNIVERSAL_ORG_TYPES)
        assert "description" in req
        assert "profiles" in req
        assert req["mandatory"] is True
        
        req = contract.get_dimension_requirements(AcceptanceDimension.TENANT_ISOLATION)
        assert req["mandatory"] is True
        
        req = contract.get_dimension_requirements(AcceptanceDimension.SCALE_MATRIX)
        assert req["mandatory"] is True

    def test_mandatory_dimensions(self):
        """Test mandatory dimensions identification."""
        from app.validation.universal_acceptance import UniversalAcceptanceContract, AcceptanceDimension
        
        contract = UniversalAcceptanceContract()
        
        mandatory = contract.mandatory_dimensions
        assert AcceptanceDimension.CANONICAL_BOUNDARY in mandatory
        assert AcceptanceDimension.TENANT_ISOLATION in mandatory
        assert AcceptanceDimension.CONCURRENCY_FAILURE_TIME in mandatory
        assert AcceptanceDimension.SCALE_MATRIX in mandatory
        assert AcceptanceDimension.EXTRAORDINARY_CAPABILITIES in mandatory

    def test_is_mandatory(self):
        """Test is_mandatory method."""
        from app.validation.universal_acceptance import UniversalAcceptanceContract, AcceptanceDimension
        
        contract = UniversalAcceptanceContract()
        
        assert contract.is_mandatory(AcceptanceDimension.CANONICAL_BOUNDARY) is True
        assert contract.is_mandatory(AcceptanceDimension.TENANT_ISOLATION) is True
        assert contract.is_mandatory(AcceptanceDimension.SCALE_MATRIX) is True
        assert contract.is_mandatory(AcceptanceDimension.CONCURRENCY_FAILURE_TIME) is True
        assert contract.is_mandatory(AcceptanceDimension.EXTRAORDINARY_CAPABILITIES) is True


class TestUniversalAcceptanceCaseExecution:
    """Test individual case execution."""

    @pytest.mark.asyncio
    async def test_case_execution_flow(self, db_session: AsyncSession):
        """Test the case execution flow."""
        from app.validation.universal_acceptance import UniversalAcceptanceMatrix, UniversalAcceptanceCase, UniversalCompanyProfile, AcceptanceDimension
        
        matrix = UniversalAcceptanceMatrix(db_session)
        
        # Create a test case
        profile = UniversalCompanyProfile(
            profile_id="test_5",
            name="Test Company",
            employee_count=5,
            topology="flat",
            industry="software",
            geography="united_states",
            multi_company=False,
            localization="en_us_only",
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        case = UniversalAcceptanceCase(
            case_id=f"test_{uuid.uuid4().hex[:8]}",
            dimension=AcceptanceDimension.UNIVERSAL_ORG_TYPES,
            profile=profile,
            scenario="Test universal org types",
            expected_result="PASS",
            verification_method="profile_generation_and_canonical_verification",
        )
        
        # Mock db for this test
        import asyncio
        matrix = UniversalAcceptanceMatrix(None)
        matrix.db = None
        
        # This will fail because db is None, but we can test the error handling
        result = await matrix._run_case(case)
        
        assert result.case_id == case.case_id
        assert result.dimension == AcceptanceDimension.UNIVERSAL_ORG_TYPES
        assert result.duration_ms >= 0


class TestUniversalAcceptanceReport:
    """Test the Universal Acceptance Report."""

    def test_report_creation(self):
        """Test report creation and serialization."""
        from app.validation.universal_acceptance import UniversalAcceptanceReport, UniversalCompanyProfile, AcceptanceDimension, AcceptanceResult, ValidationStatus, UniversalAcceptanceResult
        from datetime import datetime, timezone
        import uuid
        
        report = UniversalAcceptanceReport(
            run_id=f"ua_{uuid.uuid4().hex[:12]}",
            started_at=datetime.now(timezone.utc),
        )
        
        # Add a result
        profile = UniversalCompanyProfile(
            profile_id="test_5",
            name="Test Company",
            employee_count=5,
            topology="flat",
            industry="software",
            geography="united_states",
            multi_company=False,
            localization="en_us_only",
            accessibility="standard",
            scale_tier="startup_5",
        )
        
        result = UniversalAcceptanceResult(
            case_id=f"test_{uuid.uuid4().hex[:8]}",
            dimension=AcceptanceDimension.UNIVERSAL_ORG_TYPES,
            profile=profile,
            result=AcceptanceResult.PASS,
            status=ValidationStatus.VERIFIED,
            message="Test passed",
            evidence={"test": "data"},
            duration_ms=100,
        )
        
        # We can't easily add to report.results without the matrix, but we can test the report structure
        assert report.run_id.startswith("ua_")
        assert report.started_at is not None
        assert report.total_cases == 0

    def test_report_serialization(self):
        """Test report serialization to JSON."""
        from app.validation.universal_acceptance import UniversalAcceptanceReport
        from datetime import datetime, timezone
        import uuid
        
        report = UniversalAcceptanceReport(
            run_id=f"ua_{uuid.uuid4().hex[:12]}",
            started_at=datetime.now(timezone.utc),
        )
        
        json_str = report.to_json()
        assert "run_id" in json_str
        assert "total_cases" in json_str
        assert "pass_rate" in json_str
        
        # Test saving to file
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = report.save(tmpdir)
            saved_file = os.path.join(tmpdir, os.listdir(tmpdir)[0])
            assert os.path.exists(saved_file)
            
            with open(saved_file) as f:
                data = json.load(f)
                assert data["run_id"] == report.run_id


# Run the tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])