"""Tests for Canonical Scale Invariant Validator."""

import pytest
from unittest.mock import MagicMock, patch
from tests.scale.canonical_scale_invariants import (
    CanonicalScaleInvariantValidator,
    InvariantViolation,
    InvariantCheckResult,
    InvariantReport,
    create_invariant_validator,
)


class TestCanonicalScaleInvariantValidator:
    
    def test_validator_creation(self):
        validator = create_invariant_validator()
        assert validator is not None
        assert isinstance(validator, CanonicalScaleInvariantValidator)
    
    def test_canonical_models_defined(self):
        validator = create_invariant_validator()
        assert len(validator.CANONICAL_MODELS) > 30
        assert "employees" in validator.CANONICAL_MODELS
        assert "projects" in validator.CANONICAL_MODELS
        assert "canonical_observations" in validator.CANONICAL_MODELS
    
    def test_canonical_governance_defined(self):
        validator = create_invariant_validator()
        assert "resolve_caller_access" in validator.CANONICAL_GOVERNANCE
        assert "resolve_accessible_ids" in validator.CANONICAL_GOVERNANCE
    
    def test_company_brain_projections_defined(self):
        validator = create_invariant_validator()
        assert "get_company_context" in validator.COMPANY_BRAIN_PROJECTIONS
    
    def test_validate_canonical_model_identity(self):
        validator = create_invariant_validator()
        
        # Create mock generator with canonical entity types
        mock_generator = MagicMock()
        mock_generator._created_ids = {
            "employees": ["emp1", "emp2"],
            "projects": ["proj1"],
            "departments": ["dept1"],
        }
        
        violations = validator.validate_canonical_model_identity(mock_generator)
        # Should not violate for canonical entity types
        assert len(violations) == 0
    
    def test_validate_canonical_model_identity_non_canonical(self):
        validator = create_invariant_validator()
        
        # Create mock generator with non-canonical entity type
        mock_generator = MagicMock()
        mock_generator._created_ids = {
            "employees": ["emp1"],
            "scale_entities": ["se1", "se2"],  # Non-canonical
        }
        
        violations = validator.validate_canonical_model_identity(mock_generator)
        assert len(violations) == 1
        assert violations[0].invariant_name == "canonical_model_identity"
        assert violations[0].severity == InvariantCheckResult.FAIL
        assert "scale_entities" in str(violations[0].details)
    
    def test_validate_company_brain_boundary(self):
        validator = create_invariant_validator()
        
        # Test with scale brain attribute
        mock_generator = MagicMock()
        mock_generator._scale_brain = MagicMock()
        # Explicitly ensure _benchmark_brain is not set
        del mock_generator._benchmark_brain
        
        violations = validator.validate_company_brain_boundary(mock_generator)
        assert len(violations) == 1
        assert violations[0].invariant_name == "company_brain_boundary"
        assert violations[0].severity == InvariantCheckResult.FAIL
    
    def test_validate_company_brain_boundary_benchmark(self):
        validator = create_invariant_validator()
        
        # Test with benchmark brain attribute
        mock_generator = MagicMock()
        mock_generator._benchmark_brain = MagicMock()
        # Explicitly ensure _scale_brain is not set
        del mock_generator._scale_brain
        
        violations = validator.validate_company_brain_boundary(mock_generator)
        assert len(violations) == 1
        assert violations[0].invariant_name == "company_brain_boundary"
    
    def test_validate_company_brain_boundary_clean(self):
        validator = create_invariant_validator()
        
        # Test with clean generator - no brain attributes
        mock_generator = MagicMock()
        # Ensure neither attribute exists
        if hasattr(mock_generator, '_scale_brain'):
            del mock_generator._scale_brain
        if hasattr(mock_generator, '_benchmark_brain'):
            del mock_generator._benchmark_brain
        
        violations = validator.validate_company_brain_boundary(mock_generator)
        assert len(violations) == 0
    
    def test_invariant_violation_creation(self):
        violation = InvariantViolation(
            invariant_name="test_invariant",
            description="Test violation",
            severity=InvariantCheckResult.FAIL,
            details={"key": "value"},
            evidence={"evidence": "data"},
        )
        
        assert violation.invariant_name == "test_invariant"
        assert violation.severity == InvariantCheckResult.FAIL
        assert violation.details == {"key": "value"}
        assert violation.evidence == {"evidence": "data"}
    
    def test_invariant_report(self):
        violations = [
            InvariantViolation(
                invariant_name="test1",
                description="Test 1",
                severity=InvariantCheckResult.FAIL,
            ),
            InvariantViolation(
                invariant_name="test2",
                description="Test 2",
                severity=InvariantCheckResult.WARNING,
            ),
            InvariantViolation(
                invariant_name="test3",
                description="Test 3",
                severity=InvariantCheckResult.PASS,
            ),
        ]
        
        report = InvariantReport(
            run_id="test_run_123",
            scale_profile="10k",
            timestamp="2024-01-01T00:00:00",
            checks_passed=1,
            checks_failed=1,
            checks_warning=1,
            violations=violations,
        )
        
        assert report.overall_result == InvariantCheckResult.FAIL
        assert report.checks_passed == 1
        assert report.checks_failed == 1
        assert report.checks_warning == 1
        
        data = report.to_dict()
        assert data["run_id"] == "test_run_123"
        assert data["checks_failed"] == 1
        assert data["overall_result"] == "FAIL"
        assert len(data["violations"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])