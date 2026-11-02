"""Tests for Model Compatibility Validator."""

import pytest
from tests.scale.model_compatibility import (
    ModelCompatibilityValidator,
    create_canonical_validator,
    ValidationSeverity,
    GeneratorValidationReport,
)


class TestModelCompatibilityValidator:
    
    def test_validator_creation(self):
        validator = create_canonical_validator()
        assert validator is not None
        assert len(validator._inspected_models) > 30
    
    def test_model_registration(self):
        validator = ModelCompatibilityValidator()
        from app.models.employee import Employee
        validator.register_model(Employee)
        
        assert 'Employee' in validator._inspected_models
        metadata = validator._inspected_models['Employee']
        assert 'columns' in metadata
        assert 'primary_keys' in metadata
        assert 'id' in metadata['columns']
        assert 'organization_id' in metadata['columns']
        assert 'employee_number' in metadata['columns']
    
    def test_validate_known_model(self):
        validator = create_canonical_validator()
        report = validator.validate_generator_class(type('TestGen', (), {}))
        
        assert isinstance(report, GeneratorValidationReport)
    
    def test_validate_instance(self):
        validator = create_canonical_validator()
        from app.models.employee import Employee
        from app.core.timeutils import utcnow
        import uuid
        
        emp = Employee(
            id=uuid.uuid4().hex[:32],
            organization_id=uuid.uuid4().hex[:32],
            employee_number="E00001",
            first_name="Test",
            last_name="User",
            display_name="Test User",
            email="test@example.com",
            status="active",
        )
        
        result = validator.validate_instance(emp)
        assert result.model_name == "Employee"
        assert result.passed is True
    
    def test_validate_instance_missing_required(self):
        validator = create_canonical_validator()
        from app.models.employee import Employee
        import uuid
        
        emp = Employee(
            id=uuid.uuid4().hex[:32],
            organization_id=uuid.uuid4().hex[:32],
            first_name="Test",
            last_name="User",
            display_name="Test User",
            email="test@example.com",
        )
        
        result = validator.validate_instance(emp)
        errors = [f for f in result.field_results if f.severity == ValidationSeverity.ERROR]
        assert len(errors) > 0
        assert any('employee_number' in e.field_name for e in errors)


class TestSyncScaleGeneratorCompatibility:
    """Test SyncScaleGenerator against canonical models."""
    
    def test_generator_methods_exist(self):
        from tests.scale.generators import SyncScaleGenerator
        import inspect
        
        methods = [name for name, _ in inspect.getmembers(SyncScaleGenerator, predicate=inspect.isfunction) 
                   if name.startswith('_generate_')]
        
        expected_models = [
            'roles', 'departments', 'teams', 'employees', 'user_roles',
            'projects', 'tasks', 'goals', 'meetings', 'decisions',
            'documents', 'wiki_pages', 'policies', 'sops', 'templates',
            'conversations', 'messages',
            'budgets', 'vendors', 'invoices', 'purchase_orders', 'purchase_requests', 'expenses',
            'customers',
            'integrations',
            'security_events',
            'operations',
            'observations',
            'correlations', 'degradations', 'health_dimensions', 'slo_targets', 'freshness_checks', 'operational_targets',
            'learning', 'attention',
        ]
        
        for model in expected_models:
            method_name = f'_generate_{model}'
            assert method_name in methods, f"Missing generator method: {method_name}"
    
    def test_generator_against_canonical_models(self):
        validator = create_canonical_validator()
        from tests.scale.generators import SyncScaleGenerator
        
        report = validator.validate_generator_class(SyncScaleGenerator)
        
        print(f"\n=== Model Compatibility Report ===")
        print(f"Models validated: {len(report.model_results)}")
        print(f"Unknown models: {report.unknown_models}")
        print(f"Overall passed: {report.overall_passed}")
        
        errors = report.get_errors()
        warnings = report.get_warnings()
        
        print(f"Errors: {len(errors)}")
        for error in errors:
            print(f"  ERROR: {error.model_name}.{error.field_name}: {error.message}")
        
        print(f"Warnings: {len(warnings)}")
        for warning in warnings[:10]:
            print(f"  WARN: {warning.model_name}.{warning.field_name}: {warning.message}")
        
        assert report.overall_passed, f"Generator has {len(errors)} field compatibility errors"
    
    def test_no_unknown_models(self):
        validator = create_canonical_validator()
        from tests.scale.generators import SyncScaleGenerator
        
        report = validator.validate_generator_class(SyncScaleGenerator)
        
        assert len(report.unknown_models) == 0, f"Unknown models in generator: {report.unknown_models}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])