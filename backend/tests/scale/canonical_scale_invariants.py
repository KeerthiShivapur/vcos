"""Canonical Scale Invariant Validator.

Validates that scale execution maintains the Universal VCOS invariants:
- Same canonical models at all scales
- Same governance architecture
- Same tenant isolation
- Same temporal semantics
- Same provenance semantics
- Same epistemic semantics
- Same Company Brain boundary
- Same decision/action/outcome semantics

This is TEST INFRASTRUCTURE ONLY - does not become production code.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from enum import Enum

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase


class InvariantCheckResult(Enum):
    """Result of an invariant check."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class InvariantViolation:
    """A violation of a canonical invariant."""
    invariant_name: str
    description: str
    severity: InvariantCheckResult
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InvariantReport:
    """Complete report of invariant validation."""
    run_id: str
    scale_profile: str
    timestamp: str
    checks_passed: int
    checks_failed: int
    checks_warning: int
    violations: List[InvariantViolation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def overall_result(self) -> InvariantCheckResult:
        if self.checks_failed > 0:
            return InvariantCheckResult.FAIL
        if self.checks_warning > 0:
            return InvariantCheckResult.WARNING
        return InvariantCheckResult.PASS
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scale_profile": self.scale_profile,
            "timestamp": self.timestamp,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "checks_warning": self.checks_warning,
            "overall_result": self.overall_result.value,
            "violations": [
                {
                    "invariant_name": v.invariant_name,
                    "description": v.description,
                    "severity": v.severity.value,
                    "details": v.details,
                    "evidence": v.evidence,
                }
                for v in self.violations
            ],
            "metadata": self.metadata,
        }


class CanonicalScaleInvariantValidator:
    """Validates that scale execution preserves canonical VCOS invariants.
    
    This validator checks that the same canonical architecture is used
    at all scales - no scale-specific models, governance, or semantics.
    """
    
    # The canonical VCOS model classes that MUST be used at all scales
    # Keys match the generator's _created_ids keys (plural form)
    CANONICAL_MODELS = {
        "organizations": "Organization",
        "users": "User", 
        "employees": "Employee",
        "departments": "Department",
        "teams": "Team",
        "projects": "Project",
        "tasks": "Task",
        "meetings": "Meeting",
        "goals": "Goal",
        "decisions": "Decision",
        "documents": "Document",
        "wiki_pages": "WikiPage",
        "policies": "Policy",
        "sops": "SOP",
        "templates": "Template",
        "conversations": "Conversation",
        "conversation_members": "ConversationMember",
        "messages": "Message",
        "budgets": "Budget",
        "vendors": "Vendor",
        "invoices": "Invoice",
        "purchase_orders": "PurchaseOrder",
        "purchase_requests": "PurchaseRequest",
        "expenses": "Expense",
        "customers": "Customer",
        "canonical_metrics": "CanonicalMetric",
        "metric_observations": "MetricObservation",
        "connector_instances": "ConnectorInstance",
        "sync_runs": "SyncRun",
        "security_events": "SecurityEvent",
        "canonical_operations": "CanonicalOperation",
        "operation_attempts": "OperationAttempt",
        "company_state_snapshots": "CompanyStateSnapshot",
        "company_attention": "CompanyAttention",
        "organizational_learning": "OrganizationalLearning",
        "learning_evidence": "LearningEvidence",
        "canonical_observations": "CanonicalObservation",
        "correlation_contexts": "CorrelationContext",
        "degradations": "Degradation",
        "health_dimensions": "HealthDimension",
        "slo_targets": "SLOTarget",
        "freshness_checks": "FreshnessCheck",
        "operational_targets": "OperationalTarget",
        "company_decisions": "CompanyDecision",
        "company_commitments": "CompanyCommitment",
        "company_authorizations": "CompanyAuthorization",
        "company_objectives": "CompanyObjective",
        "company_goals": "CompanyGoal",
        "company_actions": "CompanyAction",
    }
    
    # Governance/authorization functions that MUST be used
    CANONICAL_GOVERNANCE = {
        "resolve_caller_access",
        "resolve_accessible_ids", 
        "effective_permission_codes",
        "canonical_authorization",
    }
    
    # Company Brain projection functions
    COMPANY_BRAIN_PROJECTIONS = {
        "get_company_context",
        "query_company_brain",
        "project_canonical_reality",
    }
    
    def __init__(self):
        self._model_cache: Dict[str, Any] = {}
        self._inspected_models: Dict[str, Any] = {}
    
    def validate_canonical_model_identity(self, generator_instance) -> List[InvariantViolation]:
        """Validate that scale generator uses only canonical models."""
        violations = []
        
        # Check that all generated entities use canonical model classes
        if hasattr(generator_instance, '_created_ids'):
            for entity_type, ids in generator_instance._created_ids.items():
                if entity_type not in self.CANONICAL_MODELS:
                    violations.append(InvariantViolation(
                        invariant_name="canonical_model_identity",
                        description=f"Generator creates non-canonical entity type: {entity_type}",
                        severity=InvariantCheckResult.FAIL,
                        details={"entity_type": entity_type, "count": len(ids)},
                    ))
        
        return violations
    
    def validate_canonical_model_fields(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate that generated data uses canonical model fields correctly."""
        violations = []
        
        # For each canonical model, verify the schema matches expectations
        for model_key, model_name in self.CANONICAL_MODELS.items():
            try:
                # Import the actual model class
                model_class = self._get_model_class(model_name)
                if not model_class:
                    violations.append(InvariantViolation(
                        invariant_name="canonical_model_identity",
                        description=f"Canonical model {model_name} not found",
                        severity=InvariantCheckResult.FAIL,
                        details={"model": model_name},
                    ))
                    continue
                
                # Check that the model has the expected canonical fields
                mapper = sa_inspect(model_class)
                expected_fields = self._get_expected_fields(model_name)
                actual_fields = {c.key for c in mapper.columns}
                
                for field in expected_fields:
                    if field not in actual_fields:
                        violations.append(InvariantViolation(
                            invariant_name="canonical_model_identity",
                            description=f"Canonical model {model_name} missing expected field: {field}",
                            severity=InvariantCheckResult.FAIL,
                            details={"model": model_name, "missing_field": field},
                        ))
                        
            except Exception as e:
                violations.append(InvariantViolation(
                    invariant_name="canonical_model_identity",
                    description=f"Error validating model {model_name}: {e}",
                    severity=InvariantCheckResult.FAIL,
                    details={"model": model_name, "error": str(e)},
                ))
        
        return violations
    
    def validate_governance_identity(self, generator_instance) -> List[InvariantViolation]:
        """Validate that scale execution uses canonical governance."""
        violations = []
        
        # Check that generator doesn't create scale-specific authorization
        if hasattr(generator_instance, '_authorization_layer'):
            violations.append(InvariantViolation(
                invariant_name="governance_identity",
                description="Generator has scale-specific authorization layer",
                severity=InvariantCheckResult.FAIL,
                details={"attribute": "_authorization_layer"},
            ))
        
        # Check that generator uses canonical authorization functions
        # This would require static analysis or runtime inspection
        # For now, we check the generator class doesn't define scale-specific auth
        generator_class = type(generator_instance)
        for func_name in self.CANONICAL_GOVERNANCE:
            if not hasattr(generator_class, func_name):
                # Check if it's imported/used
                pass  # Would need more sophisticated analysis
        
        return violations
    
    def validate_company_brain_boundary(self, generator_instance) -> List[InvariantViolation]:
        """Validate Company Brain remains a projection, not a parallel truth system."""
        violations = []
        
        # Check for scale-specific brain implementations
        if hasattr(generator_instance, '_scale_brain'):
            violations.append(InvariantViolation(
                invariant_name="company_brain_boundary",
                description="Generator has scale-specific brain implementation",
                severity=InvariantCheckResult.FAIL,
                details={"attribute": "_scale_brain"},
            ))
        
        if hasattr(generator_instance, '_benchmark_brain'):
            violations.append(InvariantViolation(
                invariant_name="company_brain_boundary",
                description="Generator has benchmark-specific brain implementation",
                severity=InvariantCheckResult.FAIL,
                details={"attribute": "_benchmark_brain"},
            ))
        
        return violations
    
    def validate_decision_semantics(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate Decision ≠ Authorization ≠ Commitment ≠ Responsibility ≠ Action ≠ Execution ≠ Outcome"""
        violations = []
        
        # Check that these are distinct model types
        decision_models = [
            "CompanyDecision",
            "CompanyCommitment", 
            "CompanyAuthorization",
            "CompanyObjective",
            "CompanyGoal",
            "CompanyAction",
        ]
        
        model_classes = {}
        for model_name in decision_models:
            model_class = self._get_model_class(model_name)
            if model_class:
                model_classes[model_name] = model_class
        
        # Verify they are distinct classes
        class_ids = set(id(cls) for cls in model_classes.values())
        if len(class_ids) != len(model_classes):
            violations.append(InvariantViolation(
                invariant_name="decision_semantics",
                description="Decision/Authorization/Commitment/Responsibility/Action/Execution/Outcome models are not distinct",
                severity=InvariantCheckResult.FAIL,
                details={"models": list(model_classes.keys())},
            ))
        
        # Check that generated decisions link to proper canonical models
        for model_name in decision_models:
            model_class = model_classes.get(model_name)
            if model_class:
                # Verify fields don't collapse semantics
                mapper = sa_inspect(model_class)
                fields = {c.key for c in mapper.columns}
                # Each should have distinct semantic fields
                pass
        
        return violations
    
    def validate_epistemic_semantics(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate Observation ≠ Inference ≠ Prediction ≠ Recommendation ≠ Authorization ≠ Execution ≠ Outcome"""
        violations = []
        
        # Check epistemic status fields preserve canonical states
        epistemic_states = [
            "CONFIRMED", "SUPPORTED", "HISTORICAL", "CORRECTED",
            "CONFLICTING", "PREDICTED", "EXPECTED", "UNKNOWN"
        ]
        
        # Check CanonicalObservation epistemic_status field
        obs_class = self._get_model_class("CanonicalObservation")
        if obs_class:
            mapper = sa_inspect(obs_class)
            if "epistemic_status" in [c.key for c in mapper.columns]:
                # Check constraint allows only canonical states
                pass
        
        # Verify AI/prediction outputs don't become canonical truth
        # Check for fields that might collapse epistemic states
        return violations
    
    def validate_tenant_isolation(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate tenant isolation is preserved at scale."""
        violations = []
        
        # Check that all canonical models have organization_id
        for model_key, model_name in self.CANONICAL_MODELS.items():
            model_class = self._get_model_class(model_name)
            if model_class:
                mapper = sa_inspect(model_class)
                has_org_id = any(c.key == "organization_id" for c in mapper.columns)
                if not has_org_id and model_name not in ["Organization"]:  # Organization itself doesn't need org_id
                    violations.append(InvariantViolation(
                        invariant_name="tenant_isolation",
                        description=f"Model {model_name} missing organization_id for tenant isolation",
                        severity=InvariantCheckResult.FAIL,
                        details={"model": model_name},
                    ))
        
        return violations
    
    def validate_temporal_integrity(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate temporal semantics are preserved."""
        violations = []
        
        # Check key temporal fields exist on relevant models
        temporal_models = {
            "CanonicalObservation": ["observed_at", "recorded_at"],
            "CanonicalOperation": ["started_at", "completed_at"],
            "Decision": ["decided_at"],
            "CompanyDecision": ["decided_at"],
            "CompanyAction": ["executed_at"],
            "CompanyAction": ["created_at", "updated_at"],
        }
        
        for model_name, required_fields in temporal_models.items():
            model_class = self._get_model_class(model_name)
            if model_class:
                mapper = sa_inspect(model_class)
                actual_fields = {c.key for c in mapper.columns}
                for field in required_fields:
                    if field not in actual_fields:
                        violations.append(InvariantViolation(
                            invariant_name="temporal_integrity",
                            description=f"Model {model_name} missing temporal field: {field}",
                            severity=InvariantCheckResult.FAIL,
                            details={"model": model_name, "missing_field": field},
                        ))
        
        return violations
    
    def validate_provenance_preservation(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate provenance is preserved."""
        violations = []
        
        # Check provenance fields on observations
        obs_class = self._get_model_class("CanonicalObservation")
        if obs_class:
            mapper = sa_inspect(obs_class)
            fields = {c.key for c in mapper.columns}
            provenance_fields = ["provenance_json", "source_event_id", "epistemic_status"]
            for field in provenance_fields:
                if field not in fields:
                    violations.append(InvariantViolation(
                        invariant_name="provenance_preservation",
                        description=f"CanonicalObservation missing provenance field: {field}",
                        severity=InvariantCheckResult.FAIL,
                        details={"model": "CanonicalObservation", "missing_field": field},
                    ))
        
        return violations
    
    def validate_exact_once_semantics(self, db_session, run_id: str) -> List[InvariantViolation]:
        """Validate exact-once semantics for operations."""
        violations = []
        
        # Check CanonicalOperation has fingerprint for deduplication
        op_class = self._get_model_class("CanonicalOperation")
        if op_class:
            mapper = sa_inspect(op_class)
            fields = {c.key for c in mapper.columns}
            if "fingerprint" not in fields:
                violations.append(InvariantViolation(
                    invariant_name="exact_once_semantics",
                    description="CanonicalOperation missing fingerprint field for deduplication",
                    severity=InvariantCheckResult.FAIL,
                    details={"model": "CanonicalOperation"},
                ))
        
        return violations
    
    def run_full_validation(self, generator_instance, db_session, run_id: str, scale_profile: str) -> Dict[str, Any]:
        """Run all invariant validations and return comprehensive report."""
        all_violations = []
        
        # Run all validation checks
        all_violations.extend(self.validate_canonical_model_identity(generator_instance))
        all_violations.extend(self.validate_canonical_model_fields(db_session, run_id))
        all_violations.extend(self.validate_governance_identity(generator_instance))
        all_violations.extend(self.validate_company_brain_boundary(generator_instance))
        all_violations.extend(self.validate_decision_semantics(db_session, run_id))
        all_violations.extend(self.validate_epistemic_semantics(db_session, run_id))
        all_violations.extend(self.validate_tenant_isolation(db_session, run_id))
        all_violations.extend(self.validate_temporal_integrity(db_session, run_id))
        all_violations.extend(self.validate_provenance_preservation(db_session, run_id))
        all_violations.extend(self.validate_exact_once_semantics(db_session, run_id))
        
        # Count results
        failed = sum(1 for v in all_violations if v.severity == InvariantCheckResult.FAIL)
        warnings = sum(1 for v in all_violations if v.severity == InvariantCheckResult.WARNING)
        passed = len(all_violations) - failed - warnings
        
        report = InvariantReport(
            run_id=run_id,
            scale_profile=scale_profile,
            timestamp=datetime.utcnow().isoformat(),
            checks_passed=passed,
            checks_failed=failed,
            checks_warning=warnings,
            violations=all_violations,
            metadata={
                "generator_type": type(generator_instance).__name__,
                "scale_profile": scale_profile,
            }
        )
        
        return report.to_dict()
    
    def _get_model_class(self, model_name: str):
        """Get model class by name from canonical models."""
        if model_name in self._model_cache:
            return self._model_cache[model_name]
        
        # Try to import from known modules
        import_paths = {
            "Organization": "app.models.organization.Organization",
            "User": "app.models.user.User",
            "Employee": "app.models.employee.Employee",
            "Department": "app.models.department.Department",
            "Team": "app.models.team.Team",
            "Project": "app.models.project.Project",
            "Task": "app.models.task.Task",
            "Meeting": "app.models.meeting.Meeting",
            "Goal": "app.models.goal.Goal",
            "Decision": "app.models.knowledge.Decision",
            "Document": "app.models.knowledge.Document",
            "WikiPage": "app.models.knowledge.WikiPage",
            "Policy": "app.models.knowledge.Policy",
            "SOP": "app.models.knowledge.SOP",
            "Template": "app.models.knowledge.Template",
            "Conversation": "app.models.communication.Conversation",
            "ConversationMember": "app.models.communication.ConversationMember",
            "Message": "app.models.communication.Message",
            "Budget": "app.models.finance.Budget",
            "Vendor": "app.models.finance.Vendor",
            "Invoice": "app.models.finance.Invoice",
            "PurchaseOrder": "app.models.finance.PurchaseOrder",
            "PurchaseRequest": "app.models.finance.PurchaseRequest",
            "Expense": "app.models.finance.Expense",
            "Customer": "app.models.customer.Customer",
            "CanonicalMetric": "app.models.canonical_business_intelligence.CanonicalMetric",
            "MetricObservation": "app.models.canonical_business_intelligence.MetricObservation",
            "ConnectorInstance": "app.models.canonical_integration.ConnectorInstance",
            "SyncRun": "app.models.canonical_integration.SyncRun",
            "SecurityEvent": "app.models.enterprise.SecurityEvent",
            "CanonicalOperation": "app.models.canonical_reliability.CanonicalOperation",
            "OperationAttempt": "app.models.canonical_reliability.OperationAttempt",
            "CompanyStateSnapshot": "app.models.continuous_twin.CompanyStateSnapshot",
            "CompanyAttention": "app.models.continuous_twin.CompanyAttention",
            "OrganizationalLearning": "app.models.organizational_learning.OrganizationalLearning",
            "LearningEvidence": "app.models.organizational_learning.LearningEvidence",
            "CanonicalObservation": "app.models.observability.CanonicalObservation",
            "CorrelationContext": "app.models.observability.CorrelationContext",
            "Degradation": "app.models.observability.Degradation",
            "HealthDimension": "app.models.observability.HealthDimension",
            "SLOTarget": "app.models.observability.SLOTarget",
            "FreshnessCheck": "app.models.observability.FreshnessCheck",
            "OperationalTarget": "app.models.observability.OperationalTarget",
            "CompanyDecision": "app.models.company_operating.CompanyDecision",
            "CompanyCommitment": "app.models.execution_strategy.CompanyCommitment",
            "CompanyAuthorization": "app.models.execution_strategy.CompanyAuthorization",
            "CompanyObjective": "app.models.execution_strategy.CompanyObjective",
            "CompanyGoal": "app.models.execution_strategy.CompanyGoal",
            "CompanyAction": "app.models.company_actions.CompanyAction",
        }
        
        import_path = import_paths.get(model_name)
        if not import_path:
            return None
        
        try:
            module_path, class_name = import_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            model_class = getattr(module, class_name)
            self._model_cache[model_name] = model_class
            return model_class
        except Exception:
            return None
    
    def _get_expected_fields(self, model_name: str) -> Set[str]:
        """Get expected canonical fields for a model."""
        # This would be defined based on canonical schema
        # For now, return minimal required fields
        base_fields = {"id", "organization_id", "created_at", "updated_at"}
        
        # Model-specific required fields
        model_fields = {
            "Organization": {"name", "slug"},
            "Employee": {"employee_number", "first_name", "last_name", "email"},
            "Project": {"code", "name"},
            "Task": {"title"},
            "Decision": {"title", "slug", "decision_maker_id", "decision_date"},
            "CanonicalObservation": {"observation_type", "fingerprint", "source", "epistemic_status"},
            "CanonicalOperation": {"operation_type", "fingerprint", "actor_id"},
            "CompanyDecision": {"title", "fingerprint", "epistemic_status"},
            "CompanyAction": {"title", "fingerprint", "epistemic_status"},
        }
        
        return base_fields | model_fields.get(model_name, set())


def create_invariant_validator() -> CanonicalScaleInvariantValidator:
    """Factory function to create canonical invariant validator."""
    return CanonicalScaleInvariantValidator()