"""Deterministic Semantic Sampling for Scale Validation.

For high-cardinality datasets, use deterministic seeded sampling to validate
semantic correctness without exhaustive validation becoming the bottleneck.
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Callable
from datetime import datetime
from enum import Enum

from sqlalchemy import select


class SamplingStrategy(Enum):
    """Sampling strategies for semantic validation."""
    DETERMINISTIC_UNIFORM = "deterministic_uniform"
    STRATIFIED_BY_TYPE = "stratified_by_type"
    STRATIFIED_BY_DEPARTMENT = "stratified_by_department"
    STRATIFIED_BY_TEAM = "stratified_by_team"
    EDGE_CASE_FOCUS = "edge_case_focus"


@dataclass
class SampleSpec:
    """Specification for a deterministic sample."""
    entity_type: str
    sample_size: int
    strategy: SamplingStrategy
    seed: int
    filters: Dict[str, Any] = field(default_factory=dict)
    
    def get_hash(self) -> str:
        """Get deterministic hash for this sample spec."""
        content = f"{self.entity_type}|{self.sample_size}|{self.strategy.value}|{self.seed}|{str(self.filters)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SemanticSampleResult:
    """Result of semantic sampling validation."""
    spec: SampleSpec
    sampled_ids: List[str]
    total_population: int
    validation_checks: Dict[str, bool]
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    passed: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec": {
                "entity_type": self.spec.entity_type,
                "sample_size": self.spec.sample_size,
                "strategy": self.spec.strategy.value,
                "seed": self.spec.seed,
                "filters": self.spec.filters,
                "hash": self.spec.get_hash(),
            },
            "sampled_ids": self.sampled_ids,
            "total_population": self.total_population,
            "validation_checks": self.validation_checks,
            "anomalies": self.anomalies,
            "passed": self.passed,
        }


class DeterministicSampler:
    """Deterministic sampler using seeded random selection.
    
    Uses per-call RNG instances to ensure each sample call is independent
    and reproducible, while caching the seeds for consistency.
    """
    
    def __init__(self, base_seed: int = 42):
        self.base_seed = base_seed
        self._seed_cache: Dict[str, int] = {}
    
    def _get_seed(self, sample_spec: SampleSpec) -> int:
        """Get deterministic seed for a sample spec."""
        cache_key = sample_spec.get_hash()
        if cache_key not in self._seed_cache:
            self._seed_cache[cache_key] = sample_spec.seed
        return self._seed_cache[cache_key]
    
    def _create_rng(self, sample_spec: SampleSpec) -> random.Random:
        """Create a fresh RNG for a sample call."""
        seed = self._get_seed(sample_spec)
        return random.Random(seed)
    
    def sample_uniform(
        self,
        population: List[Any],
        sample_spec: SampleSpec,
        id_extractor: Callable[[Any], str],
    ) -> List[str]:
        """Uniform random sample with deterministic seed."""
        rng = self._create_rng(sample_spec)
        sample_size = min(sample_spec.sample_size, len(population))
        sampled = rng.sample(population, sample_size)
        return [id_extractor(item) for item in sampled]
    
    def sample_stratified(
        self,
        population: List[Any],
        sample_spec: SampleSpec,
        id_extractor: Callable[[Any], str],
        stratum_extractor: Callable[[Any], str],
    ) -> List[str]:
        """Stratified sample with deterministic seed."""
        rng = self._create_rng(sample_spec)
        
        # Group by stratum
        strata: Dict[str, List[Any]] = {}
        for item in population:
            stratum = stratum_extractor(item)
            if stratum not in strata:
                strata[stratum] = []
            strata[stratum].append(item)
        
        # Sample proportionally from each stratum
        sampled_ids = []
        total_pop = len(population)
        for stratum, items in strata.items():
            stratum_size = max(1, int(len(items) / total_pop * sample_spec.sample_size))
            stratum_size = min(stratum_size, len(items))
            if stratum_size > 0:
                sampled = rng.sample(items, stratum_size)
                sampled_ids.extend([id_extractor(item) for item in sampled])
        
        return sampled_ids[:sample_spec.sample_size]


class SemanticValidator:
    """Validates semantic correctness using deterministic sampling."""
    
    def __init__(self, db_session, run_seed: int = 42):
        self.db = db_session
        self.run_seed = run_seed
        self.sampler = DeterministicSampler(base_seed=run_seed)
        self.results: List[SemanticSampleResult] = []
    
    def _build_sample_spec(
        self,
        entity_type: str,
        sample_size: int,
        strategy: SamplingStrategy = SamplingStrategy.DETERMINISTIC_UNIFORM,
        filters: Optional[Dict[str, Any]] = None,
    ) -> SampleSpec:
        """Build a deterministic sample spec."""
        return SampleSpec(
            entity_type=entity_type,
            sample_size=sample_size,
            strategy=strategy,
            seed=self.run_seed + hash(entity_type) % 10000,
            filters=filters or {},
        )
    
    def validate_employee_semantics(
        self,
        sample_size: int = 100,
        strategy: SamplingStrategy = SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
    ) -> SemanticSampleResult:
        """Validate employee semantic correctness."""
        from app.models.employee import Employee
        from app.models.department import Department
        
        spec = self._build_sample_spec("employee", sample_size, strategy)
        
        # Get all employees
        all_employees = self.db.execute(
            select(Employee).where(Employee.organization_id.is_not(None))
        ).scalars().all()
        
        total = len(all_employees)
        if total == 0:
            return SemanticSampleResult(
                spec=spec,
                sampled_ids=[],
                total_population=0,
                validation_checks={},
                passed=False,
                anomalies=[{"type": "empty_population", "entity": "employee"}],
            )
        
        # Sample
        if strategy == SamplingStrategy.STRATIFIED_BY_DEPARTMENT:
            sampled_ids = self.sampler.sample_stratified(
                all_employees, spec,
                id_extractor=lambda e: e.id,
                stratum_extractor=lambda e: e.department_id or "no_department",
            )
        else:
            sampled_ids = self.sampler.sample_uniform(
                all_employees, spec,
                id_extractor=lambda e: e.id,
            )
        
        # Validate sampled employees
        checks = {}
        anomalies = []
        
        for emp_id in sampled_ids:
            emp = self.db.get(Employee, emp_id)
            if not emp:
                anomalies.append({"type": "missing_entity", "id": emp_id})
                continue
            
            # Check required fields
            checks.setdefault("has_employee_number", True)
            if not emp.employee_number:
                checks["has_employee_number"] = False
                anomalies.append({"type": "missing_field", "field": "employee_number", "id": emp_id})
            
            checks.setdefault("has_email", True)
            if not emp.email:
                checks["has_email"] = False
                anomalies.append({"type": "missing_field", "field": "email", "id": emp_id})
            
            checks.setdefault("has_valid_status", True)
            if emp.status not in ["active", "probation", "notice", "on_leave", "terminated"]:
                checks["has_valid_status"] = False
                anomalies.append({"type": "invalid_enum", "field": "status", "value": emp.status, "id": emp_id})
            
            # Check department FK
            if emp.department_id:
                dept = self.db.get(Department, emp.department_id)
                if not dept:
                    checks.setdefault("valid_department_fk", True)
                    checks["valid_department_fk"] = False
                    anomalies.append({"type": "broken_fk", "field": "department_id", "id": emp_id, "target": emp.department_id})
        
        passed = all(checks.values()) and len(anomalies) == 0
        
        result = SemanticSampleResult(
            spec=spec,
            sampled_ids=sampled_ids,
            total_population=total,
            validation_checks=checks,
            anomalies=anomalies,
            passed=passed,
        )
        self.results.append(result)
        return result
    
    def validate_project_semantics(
        self,
        sample_size: int = 50,
    ) -> SemanticSampleResult:
        """Validate project semantic correctness."""
        from app.models.project import Project
        from app.models.employee import Employee
        
        spec = self._build_sample_spec("project", sample_size)
        
        all_projects = self.db.execute(
            select(Project).where(Project.organization_id.is_not(None))
        ).scalars().all()
        
        total = len(all_projects)
        if total == 0:
            return SemanticSampleResult(
                spec=spec,
                sampled_ids=[],
                total_population=0,
                validation_checks={},
                passed=False,
                anomalies=[{"type": "empty_population", "entity": "project"}],
            )
        
        sampled_ids = self.sampler.sample_uniform(
            all_projects, spec,
            id_extractor=lambda p: p.id,
        )
        
        checks = {}
        anomalies = []
        
        for proj_id in sampled_ids:
            proj = self.db.get(Project, proj_id)
            if not proj:
                anomalies.append({"type": "missing_entity", "id": proj_id})
                continue
            
            checks.setdefault("has_code", True)
            if not proj.code:
                checks["has_code"] = False
                anomalies.append({"type": "missing_field", "field": "code", "id": proj_id})
            
            checks.setdefault("has_owner_fk", True)
            if proj.owner_id:
                owner = self.db.get(Employee, proj.owner_id)
                if not owner:
                    checks["has_owner_fk"] = False
                    anomalies.append({"type": "broken_fk", "field": "owner_id", "id": proj_id, "target": proj.owner_id})
            
            checks.setdefault("valid_status", True)
            valid_statuses = ["planning", "active", "on_hold", "completed", "cancelled"]
            if proj.status not in valid_statuses:
                checks["valid_status"] = False
                anomalies.append({"type": "invalid_enum", "field": "status", "value": proj.status, "id": proj_id})
        
        passed = all(checks.values()) and len(anomalies) == 0
        
        result = SemanticSampleResult(
            spec=spec,
            sampled_ids=sampled_ids,
            total_population=total,
            validation_checks=checks,
            anomalies=anomalies,
            passed=passed,
        )
        self.results.append(result)
        return result
    
    def validate_task_semantics(
        self,
        sample_size: int = 100,
    ) -> SemanticSampleResult:
        """Validate task semantic correctness."""
        from app.models.task import Task
        from app.models.employee import Employee
        from app.models.project import Project
        
        spec = self._build_sample_spec("task", sample_size)
        
        all_tasks = self.db.execute(
            select(Task).where(Task.organization_id.is_not(None))
        ).scalars().all()
        
        total = len(all_tasks)
        if total == 0:
            return SemanticSampleResult(
                spec=spec,
                sampled_ids=[],
                total_population=0,
                validation_checks={},
                passed=False,
                anomalies=[{"type": "empty_population", "entity": "task"}],
            )
        
        sampled_ids = self.sampler.sample_uniform(
            all_tasks, spec,
            id_extractor=lambda t: t.id,
        )
        
        checks = {}
        anomalies = []
        
        for task_id in sampled_ids:
            task = self.db.get(Task, task_id)
            if not task:
                anomalies.append({"type": "missing_entity", "id": task_id})
                continue
            
            checks.setdefault("has_title", True)
            if not task.title:
                checks["has_title"] = False
                anomalies.append({"type": "missing_field", "field": "title", "id": task_id})
            
            checks.setdefault("valid_status", True)
            valid_statuses = ["pending", "in_progress", "blocked", "done", "cancelled"]
            if task.status not in valid_statuses:
                checks["valid_status"] = False
                anomalies.append({"type": "invalid_enum", "field": "status", "value": task.status, "id": task_id})
            
            checks.setdefault("valid_priority", True)
            valid_priorities = ["low", "medium", "high", "critical"]
            if task.priority not in valid_priorities:
                checks["valid_priority"] = False
                anomalies.append({"type": "invalid_enum", "field": "priority", "value": task.priority, "id": task_id})
            
            # Check project FK
            if task.project_id:
                proj = self.db.get(Project, task.project_id)
                if not proj:
                    checks.setdefault("valid_project_fk", True)
                    checks["valid_project_fk"] = False
                    anomalies.append({"type": "broken_fk", "field": "project_id", "id": task_id, "target": task.project_id})
            
            # Check assignee FK
            if task.assignee_id:
                assignee = self.db.get(Employee, task.assignee_id)
                if not assignee:
                    checks.setdefault("valid_assignee_fk", True)
                    checks["valid_assignee_fk"] = False
                    anomalies.append({"type": "broken_fk", "field": "assignee_id", "id": task_id, "target": task.assignee_id})
        
        passed = all(checks.values()) and len(anomalies) == 0
        
        result = SemanticSampleResult(
            spec=spec,
            sampled_ids=sampled_ids,
            total_population=total,
            validation_checks=checks,
            anomalies=anomalies,
            passed=passed,
        )
        self.results.append(result)
        return result
    
    def validate_decision_semantics(
        self,
        sample_size: int = 50,
    ) -> SemanticSampleResult:
        """Validate decision semantic correctness."""
        from app.models.knowledge import Decision
        from app.models.employee import Employee
        
        spec = self._build_sample_spec("decision", sample_size)
        
        all_decisions = self.db.execute(
            select(Decision).where(Decision.organization_id.is_not(None))
        ).scalars().all()
        
        total = len(all_decisions)
        if total == 0:
            return SemanticSampleResult(
                spec=spec,
                sampled_ids=[],
                total_population=0,
                validation_checks={},
                passed=False,
                anomalies=[{"type": "empty_population", "entity": "decision"}],
            )
        
        sampled_ids = self.sampler.sample_uniform(
            all_decisions, spec,
            id_extractor=lambda d: d.id,
        )
        
        checks = {}
        anomalies = []
        
        for dec_id in sampled_ids:
            dec = self.db.get(Decision, dec_id)
            if not dec:
                anomalies.append({"type": "missing_entity", "id": dec_id})
                continue
            
            checks.setdefault("has_slug", True)
            if not dec.slug:
                checks["has_slug"] = False
                anomalies.append({"type": "missing_field", "field": "slug", "id": dec_id})
            
            checks.setdefault("has_decision_maker", True)
            if dec.decision_maker_id:
                dm = self.db.get(Employee, dec.decision_maker_id)
                if not dm:
                    checks["has_decision_maker"] = False
                    anomalies.append({"type": "broken_fk", "field": "decision_maker_id", "id": dec_id, "target": dec.decision_maker_id})
            
            checks.setdefault("valid_status", True)
            valid_statuses = ["proposed", "approved", "rejected", "implemented", "deferred"]
            if dec.status not in valid_statuses:
                checks["valid_status"] = False
                anomalies.append({"type": "invalid_enum", "field": "status", "value": dec.status, "id": dec_id})
        
        passed = all(checks.values()) and len(anomalies) == 0
        
        result = SemanticSampleResult(
            spec=spec,
            sampled_ids=sampled_ids,
            total_population=total,
            validation_checks=checks,
            anomalies=anomalies,
            passed=passed,
        )
        self.results.append(result)
        return result
    
    def validate_finance_semantics(
        self,
        sample_size: int = 50,
    ) -> SemanticSampleResult:
        """Validate finance semantic correctness."""
        from app.models.finance import Invoice, PurchaseOrder, Expense, Budget, Vendor
        
        # Validate invoices
        spec = self._build_sample_spec("invoice", sample_size)
        
        all_invoices = self.db.execute(
            select(Invoice).where(Invoice.organization_id.is_not(None))
        ).scalars().all()
        
        total = len(all_invoices)
        if total == 0:
            return SemanticSampleResult(
                spec=spec,
                sampled_ids=[],
                total_population=0,
                validation_checks={},
                passed=False,
                anomalies=[{"type": "empty_population", "entity": "invoice"}],
            )
        
        sampled_ids = self.sampler.sample_uniform(
            all_invoices, spec,
            id_extractor=lambda i: i.id,
        )
        
        checks = {}
        anomalies = []
        
        for inv_id in sampled_ids:
            inv = self.db.get(Invoice, inv_id)
            if not inv:
                anomalies.append({"type": "missing_entity", "id": inv_id})
                continue
            
            checks.setdefault("has_invoice_number", True)
            if not inv.invoice_number:
                checks["has_invoice_number"] = False
                anomalies.append({"type": "missing_field", "field": "invoice_number", "id": inv_id})
            
            checks.setdefault("valid_direction", True)
            valid_directions = ["payable", "receivable"]
            if inv.direction not in valid_directions:
                checks["valid_direction"] = False
                anomalies.append({"type": "invalid_enum", "field": "direction", "value": inv.direction, "id": inv_id})
            
            checks.setdefault("valid_status", True)
            valid_statuses = ["draft", "pending", "approved", "paid", "overdue", "void", "cancelled"]
            if inv.status not in valid_statuses:
                checks["valid_status"] = False
                anomalies.append({"type": "invalid_enum", "field": "status", "value": inv.status, "id": inv_id})
            
            # Vendor FK
            if inv.vendor_id:
                vendor = self.db.get(Vendor, inv.vendor_id)
                if not vendor:
                    checks.setdefault("valid_vendor_fk", True)
                    checks["valid_vendor_fk"] = False
                    anomalies.append({"type": "broken_fk", "field": "vendor_id", "id": inv_id, "target": inv.vendor_id})
        
        passed = all(checks.values()) and len(anomalies) == 0
        
        result = SemanticSampleResult(
            spec=spec,
            sampled_ids=sampled_ids,
            total_population=total,
            validation_checks=checks,
            anomalies=anomalies,
            passed=passed,
        )
        self.results.append(result)
        return result
    
    def run_all_validations(
        self,
        employee_sample: int = 100,
        project_sample: int = 50,
        task_sample: int = 100,
        decision_sample: int = 50,
        finance_sample: int = 50,
    ) -> List[SemanticSampleResult]:
        """Run all semantic validations."""
        self.validate_employee_semantics(employee_sample)
        self.validate_project_semantics(project_sample)
        self.validate_task_semantics(task_sample)
        self.validate_decision_semantics(decision_sample)
        self.validate_finance_semantics(finance_sample)
        return self.results
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all validation results."""
        total_checks = 0
        passed_checks = 0
        total_anomalies = 0
        
        for result in self.results:
            total_checks += len(result.validation_checks)
            passed_checks += sum(1 for v in result.validation_checks.values() if v)
            total_anomalies += len(result.anomalies)
        
        return {
            "total_validations": len(self.results),
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "check_pass_rate": passed_checks / total_checks if total_checks > 0 else 0,
            "total_anomalies": total_anomalies,
            "all_passed": all(r.passed for r in self.results),
            "results": [r.to_dict() for r in self.results],
        }