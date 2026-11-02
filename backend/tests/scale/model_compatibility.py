"""Model Compatibility Validator for Scale Generation.

Validates that SyncScaleGenerator produces entities compatible with
canonical SQLAlchemy models. Does NOT duplicate model definitions.
"""

import ast
import inspect
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase


class ValidationSeverity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class FieldValidationResult:
    model_name: str
    field_name: str
    severity: ValidationSeverity
    message: str
    generator_value: Any = None
    model_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelValidationResult:
    model_name: str
    field_results: List[FieldValidationResult]
    passed: bool = True
    
    def __post_init__(self):
        self.passed = all(r.severity != ValidationSeverity.ERROR for r in self.field_results)


@dataclass
class GeneratorValidationReport:
    """Complete validation report for a generator against canonical models."""
    model_results: Dict[str, ModelValidationResult]
    unknown_models: List[str]
    overall_passed: bool
    
    def __post_init__(self):
        self.overall_passed = all(r.passed for r in self.model_results.values()) and len(self.unknown_models) == 0
    
    def get_errors(self) -> List[FieldValidationResult]:
        errors = []
        for result in self.model_results.values():
            errors.extend([f for f in result.field_results if f.severity == ValidationSeverity.ERROR])
        return errors
    
    def get_warnings(self) -> List[FieldValidationResult]:
        warnings = []
        for result in self.model_results.values():
            warnings.extend([f for f in result.field_results if f.severity == ValidationSeverity.WARNING])
        return warnings


class ModelCompatibilityValidator:
    """Validates generator output against canonical SQLAlchemy models."""
    
    def __init__(self):
        self._model_cache: Dict[str, Any] = {}
        self._inspected_models: Dict[str, Any] = {}
    
    def register_model(self, model_class: Any) -> None:
        """Register a canonical SQLAlchemy model for validation."""
        mapper = sa_inspect(model_class)
        self._model_cache[model_class.__name__] = model_class
        self._inspected_models[model_class.__name__] = {
            'columns': {c.key: c for c in mapper.columns},
            'relationships': {r.key: r for r in mapper.relationships},
            'primary_keys': [c.key for c in mapper.primary_key],
            'table_name': mapper.local_table.name,
        }
    
    def register_models(self, model_classes: List[Any]) -> None:
        for model in model_classes:
            self.register_model(model)
    
    def get_model_metadata(self, model_name: str) -> Optional[Dict[str, Any]]:
        return self._inspected_models.get(model_name)
    
    def validate_generator_class(self, generator_class: Any) -> GeneratorValidationReport:
        """Validate a generator class by inspecting its _generate_* methods."""
        model_results = {}
        unknown_models = []
        
        # Map generator method suffixes to canonical model names
        method_to_model = {
            'roles': 'Role',
            'departments': 'Department',
            'teams': 'Team',
            'employees': 'Employee',
            'user_roles': 'UserRole',
            'projects': 'Project',
            'tasks': 'Task',
            'goals': 'Goal',
            'meetings': 'Meeting',
            'decisions': 'Decision',
            'documents': 'Document',
            'wiki_pages': 'WikiPage',
            'policies': 'Policy',
            'sops': 'SOP',
            'templates': 'Template',
            'conversations': 'Conversation',
            'messages': 'Message',
            'budgets': 'Budget',
            'vendors': 'Vendor',
            'invoices': 'Invoice',
            'purchase_orders': 'PurchaseOrder',
            'purchase_requests': 'PurchaseRequest',
            'expenses': 'Expense',
            'customers': 'Customer',
            'integrations': 'ConnectorInstance',
            'security_events': 'SecurityEvent',
            'operations': 'CanonicalOperation',
            'observations': 'CanonicalObservation',
            'correlations': 'CorrelationContext',
            'degradations': 'Degradation',
            'health_dimensions': 'HealthDimension',
            'slo_targets': 'SLOTarget',
            'freshness_checks': 'FreshnessCheck',
            'operational_targets': 'OperationalTarget',
            'learning': 'OrganizationalLearning',
            'attention': 'CompanyAttention',
        }
        
        for name, method in inspect.getmembers(generator_class, predicate=inspect.isfunction):
            if name.startswith('_generate_'):
                suffix = name.replace('_generate_', '')
                model_name = method_to_model.get(suffix)
                
                if model_name and model_name in self._inspected_models:
                    result = self._validate_generate_method(model_name, method)
                    model_results[model_name] = result
                elif model_name:
                    unknown_models.append(f"{suffix} -> {model_name} (not registered)")
                else:
                    unknown_models.append(suffix)
        
        return GeneratorValidationReport(
            model_results=model_results,
            unknown_models=unknown_models,
            overall_passed=False
        )
    
    def _validate_generate_method(self, model_name: str, method: Any) -> ModelValidationResult:
        """Validate a single _generate_* method against its target model."""
        metadata = self._inspected_models[model_name]
        columns = metadata['columns']
        primary_keys = metadata['primary_keys']
        field_results = []
        
        source = textwrap.dedent(inspect.getsource(method))
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and hasattr(node.func, 'id'):
                class_name = node.func.id
                if class_name == model_name:
                    field_results.extend(self._validate_instantiation(model_name, node, columns, primary_keys))
        
        return ModelValidationResult(model_name=model_name, field_results=field_results)
    
    def _validate_instantiation(
        self, 
        model_name: str, 
        call_node: Any, 
        columns: Dict[str, Any], 
        primary_keys: List[str]
    ) -> List[FieldValidationResult]:
        results = []
        provided_fields = {kw.arg: kw.value for kw in call_node.keywords}
        
        for col_name, col in columns.items():
            if col_name in primary_keys and col_name not in provided_fields:
                continue
            
            if col_name not in provided_fields:
                if not col.nullable and col.default is None:
                    results.append(FieldValidationResult(
                        model_name=model_name,
                        field_name=col_name,
                        severity=ValidationSeverity.ERROR,
                        message=f"Required non-nullable field '{col_name}' not provided in generator",
                        model_metadata={'nullable': col.nullable, 'type': str(col.type)}
                    ))
                continue
            
            provided_value = provided_fields[col_name]
            
            if not col.nullable and provided_value is None:
                results.append(FieldValidationResult(
                    model_name=model_name,
                    field_name=col_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"Non-nullable field '{col_name}' assigned None",
                    model_metadata={'nullable': col.nullable, 'type': str(col.type)}
                ))
            
            if hasattr(col.type, 'enums') and col.type.enums:
                if hasattr(provided_value, 'value'):
                    val = provided_value.value
                elif isinstance(provided_value, str):
                    val = provided_value
                else:
                    continue
                
                if val not in col.type.enums:
                    results.append(FieldValidationResult(
                        model_name=model_name,
                        field_name=col_name,
                        severity=ValidationSeverity.WARNING,
                        message=f"Value '{val}' may not be in enum {col.type.enums}",
                        generator_value=val,
                        model_metadata={'enum_values': col.type.enums}
                    ))
        
        for provided_name in provided_fields:
            if provided_name not in columns:
                results.append(FieldValidationResult(
                    model_name=model_name,
                    field_name=provided_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"Generator provides unknown field '{provided_name}' not in canonical model",
                    model_metadata={}
                ))
        
        return results
    
    def validate_instance(self, instance: Any) -> ModelValidationResult:
        """Validate an instantiated model instance against canonical metadata."""
        model_name = instance.__class__.__name__
        if model_name not in self._inspected_models:
            return ModelValidationResult(
                model_name=model_name,
                field_results=[FieldValidationResult(
                    model_name=model_name,
                    field_name='__model__',
                    severity=ValidationSeverity.ERROR,
                    message=f"Model '{model_name}' not registered for validation"
                )]
            )
        
        metadata = self._inspected_models[model_name]
        columns = metadata['columns']
        field_results = []
        
        for col_name, col in columns.items():
            value = getattr(instance, col_name, None)
            
            if col_name in metadata['primary_keys'] and value is None:
                continue
            
            if value is None and not col.nullable and col.default is None:
                field_results.append(FieldValidationResult(
                    model_name=model_name,
                    field_name=col_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"Required field '{col_name}' is None",
                    model_metadata={'nullable': col.nullable, 'type': str(col.type)}
                ))
            
            if value is not None and hasattr(col.type, 'enums') and col.type.enums:
                val = value.value if hasattr(value, 'value') else value
                if isinstance(val, str) and val not in col.type.enums:
                    field_results.append(FieldValidationResult(
                        model_name=model_name,
                        field_name=col_name,
                        severity=ValidationSeverity.WARNING,
                        message=f"Value '{val}' may not be in enum {col.type.enums}",
                        generator_value=val,
                        model_metadata={'enum_values': col.type.enums}
                    ))
        
        return ModelValidationResult(model_name=model_name, field_results=field_results)


def create_canonical_validator() -> ModelCompatibilityValidator:
    """Create a validator with all canonical VCOS models registered."""
    validator = ModelCompatibilityValidator()
    
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.employee import Employee
    from app.models.department import Department
    from app.models.team import Team
    from app.models.role import Role, UserRole
    from app.models.project import Project
    from app.models.task import Task
    from app.models.goal import Goal
    from app.models.meeting import Meeting
    from app.models.knowledge import Decision, Document, WikiPage, Policy, SOP, Template
    from app.models.communication import Conversation, ConversationMember, Message
    from app.models.finance import Budget, Vendor, Invoice, PurchaseOrder, PurchaseRequest, Expense
    from app.models.customer import Customer
    from app.models.canonical_business_intelligence import CanonicalMetric, MetricObservation
    from app.models.canonical_integration import ConnectorInstance, SyncRun
    from app.models.enterprise import SecurityEvent
    from app.models.canonical_reliability import CanonicalOperation, OperationAttempt
    from app.models.continuous_twin import CompanyStateSnapshot, CompanyAttention
    from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
    from app.models.observability import CanonicalObservation, CorrelationContext, Degradation, HealthDimension, SLOTarget, FreshnessCheck, OperationalTarget
    from app.models.company_operating import CompanyDecision
    from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal
    from app.models.company_actions import CompanyAction
    
    models = [
        Organization, User, Employee, Department, Team, Role, UserRole,
        Project, Task, Goal, Meeting,
        Decision, Document, WikiPage, Policy, SOP, Template,
        Conversation, ConversationMember, Message,
        Budget, Vendor, Invoice, PurchaseOrder, PurchaseRequest, Expense,
        Customer,
        CanonicalMetric, MetricObservation,
        ConnectorInstance, SyncRun,
        SecurityEvent,
        CanonicalOperation, OperationAttempt,
        CompanyStateSnapshot, CompanyAttention,
        OrganizationalLearning, LearningEvidence,
        CanonicalObservation, CorrelationContext, Degradation, HealthDimension, SLOTarget, FreshnessCheck, OperationalTarget,
        CompanyDecision,
        CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal,
        CompanyAction,
    ]
    
    validator.register_models(models)
    return validator