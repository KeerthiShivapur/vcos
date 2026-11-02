"""Gate 35 — Scale Data Generators.

Deterministic generators for realistic company data at multiple scales:
5, 50, 500, 5_000, 50_000, 500_000+ employees.

Uses existing canonical models. No parallel scale-only models.
"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role, UserRole
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting
from app.models.goal import Goal
from app.models.knowledge import Decision
from app.models.knowledge import Document, WikiPage, Policy, SOP, Template
from app.models.communication import Conversation, ConversationMember, Message
from app.models.finance import Budget, Vendor, Invoice, PurchaseOrder, PurchaseRequest, Expense
from app.models.customer import Customer
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal
from app.models.company_actions import CompanyAction
from app.models.canonical_business_intelligence import CanonicalMetric, MetricObservation
from app.models.canonical_integration import ConnectorInstance, SyncRun
from app.models.enterprise import SecurityEvent
from app.models.canonical_reliability import CanonicalOperation, OperationAttempt
from app.models.continuous_twin import CompanyStateSnapshot, CompanyAttention
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.observability import CanonicalObservation, CorrelationContext, Degradation, HealthDimension, SLOTarget, FreshnessCheck, OperationalTarget
from app.core.timeutils import utcnow


# Scale definitions
SCALE_LEVELS = {
    "startup": 5,
    "small": 50,
    "medium": 500,
    "large": 5_000,
    "enterprise": 50_000,
    "mega": 500_000,
}

# Realistic distributions
DEPT_PER_EMPLOYEE = 0.1  # ~1 dept per 10 employees
TEAM_PER_DEPT = 3
PROJECT_PER_TEAM = 2
TASK_PER_PROJECT = 20
MEETING_PER_EMPLOYEE_PER_MONTH = 8
DECISION_PER_PROJECT_PER_MONTH = 3
DOCUMENT_PER_EMPLOYEE = 2
CONVERSATION_PER_EMPLOYEE = 5
MESSAGE_PER_CONVERSATION = 50
CUSTOMER_PER_100_EMPLOYEES = 10
VENDOR_PER_100_EMPLOYEES = 5
INTEGRATION_PER_10_EMPLOYEES = 1
SECURITY_EVENT_PER_100_EMPLOYEES_PER_DAY = 2
OBSERVATION_PER_EMPLOYEE_PER_DAY = 10

# Temporal distributions
YEARS_OF_HISTORY = 3
DAYS_PER_YEAR = 365


@dataclass
class ScaleConfig:
    """Configuration for a scale level."""
    name: str
    employee_count: int
    years_of_history: int = YEARS_OF_HISTORY
    include_historical: bool = True
    include_inactive: bool = True
    
    @property
    def dept_count(self) -> int:
        return max(1, int(self.employee_count * DEPT_PER_EMPLOYEE))
    
    @property
    def team_count(self) -> int:
        return max(1, self.dept_count * TEAM_PER_DEPT)
    
    @property
    def project_count(self) -> int:
        return max(1, self.team_count * PROJECT_PER_TEAM)
    
    @property
    def task_count(self) -> int:
        return max(1, self.project_count * TASK_PER_PROJECT)
    
    @property
    def meeting_count(self) -> int:
        return max(1, self.employee_count * MEETING_PER_EMPLOYEE_PER_MONTH * 12 * self.years_of_history)
    
    @property
    def decision_count(self) -> int:
        return max(1, self.project_count * DECISION_PER_PROJECT_PER_MONTH * 12 * self.years_of_history)
    
    @property
    def document_count(self) -> int:
        return max(1, self.employee_count * DOCUMENT_PER_EMPLOYEE)
    
    @property
    def conversation_count(self) -> int:
        return max(1, self.employee_count * CONVERSATION_PER_EMPLOYEE)
    
    @property
    def message_count(self) -> int:
        return max(1, self.conversation_count * MESSAGE_PER_CONVERSATION)
    
    @property
    def customer_count(self) -> int:
        return max(1, (self.employee_count // 100) * CUSTOMER_PER_100_EMPLOYEES)
    
    @property
    def vendor_count(self) -> int:
        return max(1, (self.employee_count // 100) * VENDOR_PER_100_EMPLOYEES)
    
    @property
    def integration_count(self) -> int:
        return max(1, (self.employee_count // 10) * INTEGRATION_PER_10_EMPLOYEES)
    
    @property
    def security_event_count(self) -> int:
        return max(1, (self.employee_count // 100) * SECURITY_EVENT_PER_100_EMPLOYEES_PER_DAY * DAYS_PER_YEAR * self.years_of_history)
    
    @property
    def observation_count(self) -> int:
        return max(1, self.employee_count * OBSERVATION_PER_EMPLOYEE_PER_DAY * DAYS_PER_YEAR * self.years_of_history)
    
    @property
    def goal_count(self) -> int:
        return max(1, self.employee_count // 2)
    
    @property
    def wiki_page_count(self) -> int:
        return max(1, self.employee_count // 5)
    
    @property
    def policy_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def sop_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def template_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def correlation_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def degradation_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def health_dimension_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def slo_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def freshness_check_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operational_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operation_count(self) -> int:
        return max(1, self.employee_count * 5)
    
    @property
    def learning_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def attention_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def role_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def correlation_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def degradation_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def health_dimension_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def slo_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def freshness_check_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operational_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def budget_count(self) -> int:
        return max(1, self.dept_count)
    
    @property
    def vendor_count(self) -> int:
        return max(1, (self.employee_count // 100) * VENDOR_PER_100_EMPLOYEES)
    
    @property
    def invoice_count(self) -> int:
        return max(1, self.vendor_count * 2)
    
    @property
    def purchase_order_count(self) -> int:
        return max(1, self.vendor_count)
    
    @property
    def purchase_request_count(self) -> int:
        return max(1, self.employee_count // 5)
    
    @property
    def expense_count(self) -> int:
        return max(1, self.employee_count * 2)
    
    @property
    def customer_count(self) -> int:
        return max(1, (self.employee_count // 100) * CUSTOMER_PER_100_EMPLOYEES)
    
    @property
    def conversation_count(self) -> int:
        return max(1, self.employee_count * CONVERSATION_PER_EMPLOYEE)
    
    @property
    def message_count(self) -> int:
        return max(1, self.conversation_count * MESSAGE_PER_CONVERSATION)
    
    @property
    def learning_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def attention_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def correlation_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def degradation_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def health_dimension_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def slo_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def freshness_check_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operational_target_count(self) -> int:
        return max(1, self.employee_count // 20)


# ================================================================
# Universal Scale Profile — Scale-aware density strategy
# ================================================================

class ScaleDensityStrategy(Enum):
    """Strategy for scaling data density at different organizational sizes."""
    LINEAR = "linear"                    # Direct linear scaling (current 35-E behavior)
    SUBLINEAR = "sublinear"              # Sublinear: volume grows slower than employee count
    LOGARITHMIC = "logarithmic"          # Logarithmic: volume grows logarithmically
    CAPPED = "capped"                    # Capped: volume stops growing at threshold
    REPRESENTATIVE = "representative"    # Representative: fixed sample per employee tier


@dataclass
class UniversalScaleProfile:
    """
    Universal Scale Profile — defines how canonical entities and operational volumes
    scale across organizational sizes. One architecture, parameterized by scale.
    
    This replaces the simple linear scaling in ScaleConfig with a scientifically
    defensible density model that preserves canonical semantics at all scales.
    """
    
    # Profile identity
    name: str
    employee_count: int
    organization_count: int = 1
    
    # Organizational structure
    dept_per_employee: float = 0.1
    team_per_dept: int = 3
    project_per_team: int = 2
    task_per_project: int = 20
    reporting_depth: int = 4  # CEO -> VP -> Director -> Manager -> IC
    
    # Density strategies per entity type
    observation_strategy: ScaleDensityStrategy = ScaleDensityStrategy.SUBLINEAR
    observation_base_per_employee_per_day: int = 10
    observation_max_per_employee: int = 5000  # Cap at 5K observations/employee
    
    security_event_strategy: ScaleDensityStrategy = ScaleDensityStrategy.SUBLINEAR
    security_event_base_per_100_employees_per_day: int = 2
    security_event_max_per_employee: int = 100
    
    meeting_strategy: ScaleDensityStrategy = ScaleDensityStrategy.LINEAR
    meeting_per_employee_per_month: int = 8
    
    decision_strategy: ScaleDensityStrategy = ScaleDensityStrategy.SUBLINEAR
    decision_per_project_per_month: int = 3
    decision_max_per_employee: int = 500
    
    document_strategy: ScaleDensityStrategy = ScaleDensityStrategy.LINEAR
    document_per_employee: int = 2
    
    conversation_strategy: ScaleDensityStrategy = ScaleDensityStrategy.LOGARITHMIC
    conversation_per_employee: int = 5
    conversation_max_per_employee: int = 100
    
    customer_strategy: ScaleDensityStrategy = ScaleDensityStrategy.SUBLINEAR
    customer_per_100_employees: int = 10
    customer_max_per_employee: int = 50
    
    integration_strategy: ScaleDensityStrategy = ScaleDensityStrategy.LOGARITHMIC
    integration_per_10_employees: int = 1
    integration_max_per_employee: int = 20
    
    # Historical configuration
    years_of_history: int = 3
    days_per_year: int = 365
    
    # Workload distribution
    concurrent_users_ratio: float = 0.1  # 10% of employees active concurrently
    peak_concurrency_multiplier: float = 3.0
    
    # Multi-company support
    tenant_distribution: str = "single"  # single, few, many
    
    @property
    def tenant_count(self) -> int:
        """Number of tenants (organizations) - alias for organization_count."""
        return self.organization_count
    
    @property
    def dept_count(self) -> int:
        return max(1, int(self.employee_count * self.dept_per_employee))
    
    @property
    def team_count(self) -> int:
        return max(1, self.dept_count * self.team_per_dept)
    
    @property
    def project_count(self) -> int:
        return max(1, self.team_count * self.project_per_team)
    
    @property
    def task_count(self) -> int:
        return max(1, self.project_count * self.task_per_project)
    
    @property
    def meeting_count(self) -> int:
        return max(1, self._scale(self.meeting_strategy, 
                                   self.employee_count * self.meeting_per_employee_per_month * 12 * self.years_of_history,
                                   self.employee_count * self.meeting_per_employee_per_month * 12 * self.years_of_history))
    
    @property
    def decision_count(self) -> int:
        base = self.project_count * self.decision_per_project_per_month * 12 * self.years_of_history
        return max(1, self._scale(self.decision_strategy, base, self.employee_count * self.decision_max_per_employee))
    
    @property
    def document_count(self) -> int:
        base = self.employee_count * self.document_per_employee
        return max(1, self._scale(self.document_strategy, base, base))
    
    @property
    def conversation_count(self) -> int:
        base = self.employee_count * self.conversation_per_employee
        return max(1, self._scale(self.conversation_strategy, base, self.employee_count * self.conversation_max_per_employee))
    
    @property
    def message_count(self) -> int:
        return max(1, self.conversation_count * 50)  # MESSAGE_PER_CONVERSATION
    
    @property
    def customer_count(self) -> int:
        base = (self.employee_count // 100) * self.customer_per_100_employees
        return max(1, self._scale(self.customer_strategy, base, self.employee_count * self.customer_max_per_employee))
    
    @property
    def vendor_count(self) -> int:
        return max(1, (self.employee_count // 100) * 5)
    
    @property
    def integration_count(self) -> int:
        base = (self.employee_count // 10) * self.integration_per_10_employees
        return max(1, self._scale(self.integration_strategy, base, self.employee_count * self.integration_max_per_employee))
    
    @property
    def security_event_count(self) -> int:
        base = (self.employee_count // 100) * self.security_event_base_per_100_employees_per_day * self.days_per_year * self.years_of_history
        return max(1, self._scale(self.security_event_strategy, base, self.employee_count * self.security_event_max_per_employee))
    
    @property
    def observation_count(self) -> int:
        base = self.employee_count * self.observation_base_per_employee_per_day * self.days_per_year * self.years_of_history
        return max(1, self._scale(self.observation_strategy, base, self.employee_count * self.observation_max_per_employee))
    
    @property
    def goal_count(self) -> int:
        return max(1, self.employee_count // 2)
    
    @property
    def wiki_page_count(self) -> int:
        return max(1, self.employee_count // 5)
    
    @property
    def policy_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def sop_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def template_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def correlation_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def degradation_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def health_dimension_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def slo_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def freshness_check_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operational_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operation_count(self) -> int:
        return max(1, self.employee_count * 5)
    
    @property
    def learning_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def attention_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def role_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def correlation_count(self) -> int:
        return max(1, self.employee_count // 10)
    
    @property
    def degradation_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def health_dimension_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def slo_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def freshness_check_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def operational_target_count(self) -> int:
        return max(1, self.employee_count // 20)
    
    @property
    def budget_count(self) -> int:
        return max(1, self.dept_count)
    
    @property
    def invoice_count(self) -> int:
        return max(1, self.vendor_count * 2)
    
    @property
    def purchase_order_count(self) -> int:
        return max(1, self.vendor_count)
    
    @property
    def purchase_request_count(self) -> int:
        return max(1, self.employee_count // 5)
    
    @property
    def expense_count(self) -> int:
        return max(1, self.employee_count * 2)
    
    def _scale(self, strategy: ScaleDensityStrategy, base: int, cap: int) -> int:
        """Apply scaling strategy to base value with optional cap."""
        if strategy == ScaleDensityStrategy.LINEAR:
            return min(base, cap)
        elif strategy == ScaleDensityStrategy.SUBLINEAR:
            # Square root scaling: grows slower than linear
            import math
            return min(int(math.sqrt(base) * math.sqrt(cap)), cap)
        elif strategy == ScaleDensityStrategy.LOGARITHMIC:
            # Logarithmic scaling: very slow growth
            import math
            if base <= 1:
                return 1
            return min(int(math.log(base) * math.sqrt(cap)), cap)
        elif strategy == ScaleDensityStrategy.CAPPED:
            return min(base, cap)
        elif strategy == ScaleDensityStrategy.REPRESENTATIVE:
            # Fixed representative sample per employee tier
            if self.employee_count <= 500:
                return min(base, cap)
            elif self.employee_count <= 5000:
                return min(cap // 10, cap)
            elif self.employee_count <= 50000:
                return min(cap // 100, cap)
            else:
                return min(cap // 1000, cap)
        return min(base, cap)
    
    @classmethod
    def from_scale_config(cls, config: ScaleConfig) -> "UniversalScaleProfile":
        """Create profile from existing ScaleConfig (backward compatibility)."""
        return cls(
            name=config.name,
            employee_count=config.employee_count,
            years_of_history=config.years_of_history,
        )
    
    @classmethod
    def startup(cls) -> "UniversalScaleProfile":
        return cls(name="startup", employee_count=5, years_of_history=3)
    
    @classmethod
    def small(cls) -> "UniversalScaleProfile":
        return cls(name="small", employee_count=50, years_of_history=3)
    
    @classmethod
    def medium(cls) -> "UniversalScaleProfile":
        return cls(name="medium", employee_count=500, years_of_history=3)
    
    @classmethod
    def large(cls) -> "UniversalScaleProfile":
        return cls(name="large", employee_count=5_000, years_of_history=3)
    
    @classmethod
    def enterprise(cls) -> "UniversalScaleProfile":
        return cls(name="enterprise", employee_count=50_000, years_of_history=3)
    
    @classmethod
    def mega(cls) -> "UniversalScaleProfile":
        return cls(name="mega", employee_count=500_000, years_of_history=3)
    
    @classmethod
    def multi_tenant(cls, tenant_count: int, employees_per_tenant: int) -> List["UniversalScaleProfile"]:
        """Create profiles for multi-tenant testing."""
        return [
            cls(name=f"tenant_{i}", employee_count=employees_per_tenant, organization_count=tenant_count)
            for i in range(tenant_count)
        ]


# Predefined scale profiles for 35-F
UNIVERSAL_SCALE_PROFILES = {
    "startup": UniversalScaleProfile.startup(),
    "small": UniversalScaleProfile.small(),
    "medium": UniversalScaleProfile.medium(),
    "large": UniversalScaleProfile.large(),
    "enterprise": UniversalScaleProfile.enterprise(),
    "mega": UniversalScaleProfile.mega(),
}


class ScaleGenerator:
    """Generates realistic company data at scale using canonical models."""
    
    def __init__(self, db: AsyncSession, organization_id: str, config: ScaleConfig):
        self.db = db
        self.org_id = organization_id
        self.config = config
        self.rng = random.Random(42)  # Deterministic seed
        self._created_ids: Dict[str, List[str]] = defaultdict(list)
        self._id_maps: Dict[str, Dict[str, Any]] = {}
    
    async def generate_all(self) -> Dict[str, int]:
        """Generate complete company reality at scale."""
        counts = {}
        
        # Core org structure
        counts["roles"] = await self._generate_roles()
        counts["departments"] = await self._generate_departments()
        counts["teams"] = await self._generate_teams()
        counts["employees"] = await self._generate_employees()
        counts["user_roles"] = await self._generate_user_roles()
        
        # Work structure
        counts["projects"] = await self._generate_projects()
        counts["tasks"] = await self._generate_tasks()
        counts["goals"] = await self._generate_goals()
        counts["meetings"] = await self._generate_meetings()
        counts["decisions"] = await self._generate_decisions()
        
        # Knowledge
        counts["documents"] = await self._generate_documents()
        counts["wiki_pages"] = await self._generate_wiki_pages()
        counts["policies"] = await self._generate_policies()
        counts["sops"] = await self._generate_sops()
        counts["templates"] = await self._generate_templates()
        
        # Communication
        counts["conversations"] = await self._generate_conversations()
        counts["messages"] = await self._generate_messages()
        
        # Finance
        counts["budgets"] = await self._generate_budgets()
        counts["vendors"] = await self._generate_vendors()
        counts["invoices"] = await self._generate_invoices()
        counts["purchase_orders"] = await self._generate_purchase_orders()
        counts["purchase_requests"] = await self._generate_purchase_requests()
        counts["expenses"] = await self._generate_expenses()
        
        # Customers
        counts["customers"] = await self._generate_customers()
        
        # Integrations
        counts["integrations"] = await self._generate_integrations()
        
        # Security
        counts["security_events"] = await self._generate_security_events()
        
        # Operations
        counts["operations"] = await self._generate_operations()
        
        # Observability
        counts["observations"] = await self._generate_observations()
        counts["correlations"] = await self._generate_correlations()
        counts["degradations"] = await self._generate_degradations()
        counts["health_dimensions"] = await self._generate_health_dimensions()
        counts["slo_targets"] = await self._generate_slo_targets()
        counts["freshness_checks"] = await self._generate_freshness_checks()
        counts["operational_targets"] = await self._generate_operational_targets()
        
        # Learning
        counts["learning"] = await self._generate_learning()
        
        # Attention
        counts["attention"] = await self._generate_attention()
        
        await self.db.commit()
        return counts
    
    # ================================================================
    # Core Organization
    # ================================================================
    
    async def _generate_roles(self) -> int:
        """Generate standard roles."""
        roles_data = [
            ("Admin", "admin", "Full administrative access"),
            ("Manager", "manager", "Team/department management"),
            ("Employee", "employee", "Standard employee access"),
            ("Executive", "executive", "Executive leadership access"),
            ("Finance", "finance", "Financial management"),
            ("HR", "hr", "Human resources"),
            ("IT", "it", "IT administration"),
            ("Security", "security", "Security operations"),
            ("Auditor", "auditor", "Audit and compliance"),
            ("Contractor", "contractor", "External contractor access"),
        ]
        
        for name, code, desc in roles_data:
            role = Role(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=name,
                code=code,
                description=desc,
                is_system=(code in ("admin", "employee")),
            )
            self.db.add(role)
            self._created_ids["roles"].append(role.id)
            self._id_maps.setdefault("roles", {})[code] = role.id
        
        await self.db.flush()
        return len(roles_data)
    
    async def _generate_departments(self) -> int:
        """Generate departments with realistic names."""
        dept_names = [
            "Engineering", "Product", "Design", "Sales", "Marketing",
            "Customer Success", "Finance", "HR", "Legal", "IT",
            "Security", "Operations", "Data", "Research", "Support",
        ]
        
        for i in range(min(self.config.dept_count, len(dept_names))):
            dept = Department(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=dept_names[i],
                code=dept_names[i][:3].upper(),
                description=f"{dept_names[i]} department",
            )
            self.db.add(dept)
            self._created_ids["departments"].append(dept.id)
            self._id_maps.setdefault("departments", {})[dept_names[i]] = dept.id
        
        await self.db.flush()
        return self.config.dept_count
    
    async def _generate_teams(self) -> int:
        """Generate teams within departments."""
        team_types = ["Platform", "Product", "Infrastructure", "Frontend", "Backend", 
                      "Mobile", "Data", "ML", "DevOps", "QA", "Security", "Growth"]
        
        dept_ids = self._created_ids["departments"]
        employee_ids = self._created_ids["employees"]
        
        team_counter = 0
        for dept_id in dept_ids:
            for j in range(TEAM_PER_DEPT):
                team_type = self.rng.choice(team_types)
                team_counter += 1
                team = Team(
                    id=uuid.uuid4().hex[:32],
                    organization_id=self.org_id,
                    department_id=dept_id,
                    name=f"{team_type} Team {team_counter}",
                    code=f"{team_type[:3].upper()}{team_counter}",
                    description=f"{team_type} team in department",
                    lead_id=self.rng.choice(employee_ids) if employee_ids else None,
                )
                self.db.add(team)
                self._created_ids["teams"].append(team.id)
        
        await self.db.flush()
        return self.config.team_count
    
    async def _generate_employees(self) -> int:
        """Generate employees with realistic distribution."""
        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn",
                       "Sam", "Dakota", "Jamie", "Reese", "Rowan", "Sage", "Skyler", "Tatum"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
                      "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
                      "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
        
        designations = [
            "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer",
            "Engineering Manager", "Director of Engineering", "VP Engineering",
            "Product Manager", "Senior Product Manager", "Group Product Manager",
            "Designer", "Senior Designer", "Design Lead",
            "Sales Rep", "Senior Sales Rep", "Sales Manager", "Account Executive",
            "Marketing Manager", "Growth Marketer", "Content Marketer",
            "Customer Success Manager", "Support Engineer",
            "Financial Analyst", "Controller", "FP&A Manager",
            "Recruiter", "HR Business Partner", "People Operations",
            "Legal Counsel", "Compliance Officer",
            "IT Specialist", "Systems Administrator", "DevOps Engineer",
            "Security Engineer", "Security Analyst",
            "Data Analyst", "Data Scientist", "ML Engineer",
            "Research Scientist", "Research Engineer",
        ]
        
        statuses = ["active"] * 90 + ["probation"] * 5 + ["notice"] * 3 + ["on_leave"] * 2
        employment_types = ["full_time"] * 85 + ["part_time"] * 10 + ["contractor"] * 5
        
        team_ids = self._created_ids["teams"]
        dept_ids = self._created_ids["departments"]
        employee_ids = self._created_ids["employees"]
        
        for i in range(self.config.employee_count):
            first = self.rng.choice(first_names)
            last = self.rng.choice(last_names)
            emp_num = f"E{10000 + i}"
            
            employee = Employee(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_number=emp_num,
                first_name=first,
                last_name=last,
                display_name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}{i}@company.com",
                designation=self.rng.choice(designations),
                department_id=self.rng.choice(dept_ids) if dept_ids else None,
                team_id=self.rng.choice(team_ids) if team_ids else None,
                manager_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.3 else None,
                employment_type=self.rng.choice(employment_types),
                joining_date=utcnow() - timedelta(days=self.rng.randint(0, 1000)),
                status=self.rng.choice(statuses),
            )
            self.db.add(employee)
            self._created_ids["employees"].append(employee.id)
        
        await self.db.flush()
        return self.config.employee_count
    
    async def _generate_user_roles(self) -> int:
        """Assign roles to employees."""
        role_ids = self._created_ids["roles"]
        employee_ids = self._created_ids["employees"]
        
        # Most employees get "employee" role
        employee_role_id = self._id_maps.get("roles", {}).get("employee")
        if not employee_role_id:
            return 0
        
        for emp_id in employee_ids:
            # 90% get employee role
            if self.rng.random() < 0.9:
                ur = UserRole(
                    id=uuid.uuid4().hex[:32],
                    organization_id=self.org_id,
                    user_id=emp_id,  # Simplified: user_id = employee_id for test
                    role_id=employee_role_id,
                    scope_id=None,  # Org-wide
                )
                self.db.add(ur)
            
            # 10% get manager role
            if self.rng.random() < 0.1:
                manager_role_id = self._id_maps.get("roles", {}).get("manager")
                if manager_role_id:
                    ur = UserRole(
                        id=uuid.uuid4().hex[:32],
                        organization_id=self.org_id,
                        user_id=emp_id,
                        role_id=manager_role_id,
                        scope_id=None,
                    )
                    self.db.add(ur)
        
        await self.db.flush()
        return len(employee_ids)
    
    # ================================================================
    # Work Structure
    # ================================================================
    
    async def _generate_projects(self) -> int:
        """Generate projects."""
        project_templates = [
            ("Platform Modernization", "Modernize core platform"),
            ("Mobile App v2", "Rewrite mobile application"),
            ("Data Pipeline", "Build real-time data pipeline"),
            ("Security Hardening", "Improve security posture"),
            ("Customer Portal", "New customer self-service portal"),
            ("Internal Tools", "Developer productivity tools"),
            ("ML Platform", "Machine learning infrastructure"),
            ("API Gateway", "Unified API gateway"),
            ("Analytics Dashboard", "Business intelligence dashboard"),
            ("Migration", "Cloud migration project"),
        ]
        
        statuses = ["active"] * 60 + ["planning"] * 20 + ["completed"] * 15 + ["on_hold"] * 5
        
        team_ids = self._created_ids["teams"]
        employee_ids = self._created_ids["employees"]
        
        for i in range(self.config.project_count):
            template = self.rng.choice(project_templates)
            project = Project(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"{template[0]} {i+1}",
                code=f"PRJ-{1000 + i}",
                description=template[1],
                status=self.rng.choice(statuses),
                owner_id=self.rng.choice(employee_ids) if employee_ids else None,
                team_id=self.rng.choice(team_ids) if team_ids else None,
                progress=self.rng.randint(0, 100),
                start_date=utcnow() - timedelta(days=self.rng.randint(0, 365)),
                end_date=utcnow() + timedelta(days=self.rng.randint(0, 365)),
            )
            self.db.add(project)
            self._created_ids["projects"].append(project.id)
        
        await self.db.flush()
        return self.config.project_count
    
    async def _generate_tasks(self) -> int:
        """Generate tasks for projects."""
        statuses = ["pending"] * 30 + ["in_progress"] * 40 + ["blocked"] * 10 + ["done"] * 15 + ["cancelled"] * 5
        priorities = ["low"] * 20 + ["medium"] * 50 + ["high"] * 25 + ["critical"] * 5
        
        project_ids = self._created_ids["projects"]
        employee_ids = self._created_ids["employees"]
        
        for i in range(self.config.task_count):
            project_id = self.rng.choice(project_ids) if project_ids else None
            task = Task(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                project_id=project_id,
                title=f"Task {i+1}: {self.rng.choice(['Implement', 'Fix', 'Review', 'Design', 'Test', 'Deploy'])} {self.rng.choice(['API', 'UI', 'Database', 'Auth', 'Cache', 'Queue'])}",
                description=f"Detailed description for task {i+1}",
                status=self.rng.choice(statuses),
                priority=self.rng.choice(priorities),
                assignee_id=self.rng.choice(employee_ids) if employee_ids else None,
                reporter_id=self.rng.choice(employee_ids) if employee_ids else None,
                estimate_hours=self.rng.choice([1, 2, 3, 5, 8, 13, 21]),
                due_date=utcnow() + timedelta(days=self.rng.randint(-30, 60)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(task)
            self._created_ids["tasks"].append(task.id)
        
        await self.db.flush()
        return self.config.task_count
    
    async def _generate_goals(self) -> int:
        """Generate goals."""
        goal_count = max(1, self.config.project_count * 3)
        scopes = ["org"] * 20 + ["department"] * 30 + ["team"] * 30 + ["project"] * 20
        statuses = ["active"] * 70 + ["completed"] * 20 + ["at_risk"] * 10
        
        project_ids = self._created_ids["projects"]
        team_ids = self._created_ids["teams"]
        employee_ids = self._created_ids["employees"]
        
        for i in range(goal_count):
            scope = self.rng.choice(scopes)
            goal = Goal(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Goal {i+1}: {self.rng.choice(['Increase', 'Improve', 'Reduce', 'Launch', 'Optimize'])} {self.rng.choice(['revenue', 'efficiency', 'churn', 'velocity', 'quality', 'coverage'])}",
                description=f"Strategic goal {i+1}",
                scope=scope,
                project_id=self.rng.choice(project_ids) if scope == "project" and project_ids else None,
                team_id=self.rng.choice(team_ids) if scope == "team" and team_ids else None,
                owner_id=self.rng.choice(employee_ids) if employee_ids else None,
                status=self.rng.choice(statuses),
                progress=self.rng.randint(0, 100),
                end_date=utcnow() + timedelta(days=self.rng.randint(30, 365)),
            )
            self.db.add(goal)
            self._created_ids["goals"].append(goal.id)
        
        await self.db.flush()
        return goal_count
    
    async def _generate_meetings(self) -> int:
        """Generate meetings."""
        meeting_types = ["standup", "planning", "review", "retro", "1on1", "all_hands", "sync", "decision"]
        statuses = ["scheduled"] * 40 + ["completed"] * 50 + ["cancelled"] * 10
        
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        
        for i in range(self.config.meeting_count):
            start_at = utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history), hours=self.rng.randint(0, 23))
            meeting = Meeting(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"{self.rng.choice(meeting_types).title()} - {self.rng.choice(['Weekly', 'Bi-weekly', 'Monthly', 'Quarterly', 'Ad-hoc'])} {i+1}",
                description=f"Meeting {i+1} description",
                meeting_type=self.rng.choice(meeting_types),
                status=self.rng.choice(statuses),
                organizer_id=self.rng.choice(employee_ids) if employee_ids else None,
                project_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None,
                start_at=start_at,
                end_at=start_at + timedelta(minutes=self.rng.choice([15, 30, 45, 60, 90, 120])),
                duration_minutes=self.rng.choice([15, 30, 45, 60, 90, 120]),
            )
            self.db.add(meeting)
            self._created_ids["meetings"].append(meeting.id)
        
        await self.db.flush()
        return self.config.meeting_count
    
    async def _generate_decisions(self) -> int:
        """Generate decisions."""
        statuses = ["proposed"] * 10 + ["under_review"] * 20 + ["published"] * 40 + ["archived"] * 10 + ["draft"] * 20
        
        project_ids = self._created_ids["projects"]
        employee_ids = self._created_ids["employees"]
        
        for i in range(self.config.decision_count):
            title = f"Decision {i+1}: {self.rng.choice(['Approve', 'Reject', 'Defer', 'Modify', 'Escalate'])} {self.rng.choice(['budget', 'hiring', 'architecture', 'vendor', 'process', 'policy'])}"
            slug = f"decision-{i+1}-{uuid.uuid4().hex[:8]}"
            decision = Decision(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                project_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.5 else None,
                title=title,
                slug=slug,
                description=f"Decision rationale {i+1}",
                status=self.rng.choice(statuses),
                decision_maker_id=self.rng.choice(employee_ids) if employee_ids else None,
                decision_date=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)) if self.rng.random() < 0.6 else None,
                impact="medium",
            )
            self.db.add(decision)
            self._created_ids["decisions"].append(decision.id)
        
        await self.db.flush()
        return self.config.decision_count
    
    # ================================================================
    # Knowledge
    # ================================================================
    
    async def _generate_documents(self) -> int:
        """Generate documents."""
        categories = ["architecture", "process", "guide", "reference", "spec", "runbook", "adr"]
        statuses = ["published"] * 70 + ["draft"] * 20 + ["archived"] * 10
        
        project_ids = self._created_ids["projects"]
        employee_ids = self._created_ids["employees"]
        
        for i in range(self.config.document_count):
            title = f"Document {i+1}: {self.rng.choice(categories).title()} - {self.rng.choice(['API', 'Database', 'Auth', 'Deployment', 'Monitoring', 'Security'])}"
            slug = f"document-{i+1}-{uuid.uuid4().hex[:8]}"
            doc = Document(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                project_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.5 else None,
                title=title,
                slug=slug,
                description=f"Document {i+1} description",
                category=self.rng.choice(categories),
                status=self.rng.choice(statuses),
                author_id=self.rng.choice(employee_ids) if employee_ids else None,
                content=f"# Document {i+1}\n\nContent for {self.rng.choice(categories)} document.\n\n## Section 1\n\nDetails here.\n\n## Section 2\n\nMore details.",
                version="1.0",
            )
            self.db.add(doc)
            self._created_ids["documents"].append(doc.id)
        
        await self.db.flush()
        return self.config.document_count
    
    async def _generate_wiki_pages(self) -> int:
        """Generate wiki pages."""
        count = max(1, self.config.document_count // 2)
        
        for i in range(count):
            title = f"Wiki: {self.rng.choice(['Onboarding', 'Architecture', 'Process', 'FAQ', 'Glossary', 'Runbook'])} {i+1}"
            slug = f"wiki-{i+1}-{uuid.uuid4().hex[:8]}"
            page = WikiPage(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=title,
                slug=slug,
                content=f"# Wiki Page {i+1}\n\nContent for wiki page.",
                status=self.rng.choice(["published", "draft", "archived"]),
            )
            self.db.add(page)
            self._created_ids["wiki_pages"].append(page.id)
        
        await self.db.flush()
        return count
    
    async def _generate_policies(self) -> int:
        """Generate policies."""
        count = max(1, self.config.employee_count // 50)
        
        for i in range(count):
            title = f"Policy {i+1}: {self.rng.choice(['Security', 'Privacy', 'Access', 'Data', 'Compliance', 'HR', 'Finance'])} Policy"
            slug = f"policy-{i+1}-{uuid.uuid4().hex[:8]}"
            policy = Policy(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=title,
                slug=slug,
                description=f"Policy {i+1} description",
                category=self.rng.choice(["security", "privacy", "access", "data", "compliance", "hr", "finance"]),
                status=self.rng.choice(["published", "draft", "under_review"]),
                version="1.0",
            )
            self.db.add(policy)
            self._created_ids["policies"].append(policy.id)
        
        await self.db.flush()
        return count
    
    async def _generate_sops(self) -> int:
        """Generate SOPs."""
        count = max(1, self.config.employee_count // 30)
        
        for i in range(count):
            title = f"SOP {i+1}: {self.rng.choice(['Deployment', 'Incident Response', 'Onboarding', 'Offboarding', 'Access Request', 'Code Review', 'Release'])} Procedure"
            slug = f"sop-{i+1}-{uuid.uuid4().hex[:8]}"
            sop = SOP(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=title,
                slug=slug,
                description=f"SOP {i+1} description",
                category=self.rng.choice(["operations", "security", "hr", "engineering", "finance"]),
                status=self.rng.choice(["published", "draft", "under_review"]),
            )
            self.db.add(sop)
            self._created_ids["sops"].append(sop.id)
        
        await self.db.flush()
        return count
    
    async def _generate_templates(self) -> int:
        """Generate templates."""
        count = max(1, self.config.employee_count // 40)
        
        for i in range(count):
            title = f"Template {i+1}: {self.rng.choice(['Project Plan', 'RFP', 'Contract', 'Report', 'Presentation', 'Spec'])} Template"
            slug = f"template-{i+1}-{uuid.uuid4().hex[:8]}"
            template = Template(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=title,
                slug=slug,
                description=f"Template {i+1} description",
                category=self.rng.choice(["project", "procurement", "legal", "reporting", "engineering"]),
                content=f"# Template {i+1}\n\nTemplate content here.",
                status=self.rng.choice(["published", "draft"]),
            )
            self.db.add(template)
            self._created_ids["templates"].append(template.id)
        
        await self.db.flush()
        return count
    
    # ================================================================
    # Communication
    # ================================================================
    
    async def _generate_conversations(self) -> int:
        """Generate conversations."""
        conv_types = ["dm", "channel", "group"]
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        
        for i in range(self.config.conversation_count):
            conv = Conversation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                type=self.rng.choice(conv_types),
                title=f"Conversation {i+1}" if self.rng.random() < 0.5 else None,
                channel_kind=self.rng.choice(["channel", "group", None]) if self.rng.random() < 0.5 else None,
                channel_key=f"ch-{uuid.uuid4().hex[:8]}" if self.rng.random() < 0.3 else None,
                community_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None,
                is_archived=self.rng.random() < 0.1,
                message_count=self.rng.randint(1, 200),
            )
            self.db.add(conv)
            self._created_ids["conversations"].append(conv.id)
        
        await self.db.flush()
        
        # Add members
        for conv_id in self._created_ids["conversations"]:
            member_count = self.rng.randint(2, min(10, len(employee_ids)))
            members = self.rng.sample(employee_ids, member_count)
            for emp_id in members:
                member = ConversationMember(
                    id=uuid.uuid4().hex[:32],
                    organization_id=self.org_id,
                    conversation_id=conv_id,
                    employee_id=emp_id,
                    role=self.rng.choice(["member", "admin", "owner"]),
                )
                self.db.add(member)
        
        await self.db.flush()
        return self.config.conversation_count
    
    async def _generate_messages(self) -> int:
        """Generate messages in conversations."""
        employee_ids = self._created_ids["employees"]
        conversation_ids = self._created_ids["conversations"]
        
        # Generate messages with temporal distribution
        for i in range(self.config.message_count):
            conv_id = self.rng.choice(conversation_ids)
            sender_id = self.rng.choice(employee_ids)
            
            # Temporal distribution over history
            days_ago = self.rng.randint(0, 365 * self.config.years_of_history)
            hours_ago = self.rng.randint(0, 23)
            minutes_ago = self.rng.randint(0, 59)
            
            message = Message(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                conversation_id=conv_id,
                sender_id=sender_id,
                content=f"Message {i+1}: {self.rng.choice(['Hello team', 'Update on', 'Question about', 'FYI:', 'Action needed:', 'Review:', 'Deployed:', 'Fixed:'])} {self.rng.choice(['project', 'task', 'meeting', 'decision', 'document', 'issue', 'feature', 'bug'])}",
                deleted=False,
                created_at=utcnow() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago),
            )
            self.db.add(message)
            self._created_ids["messages"].append(message.id)
        
        await self.db.flush()
        return self.config.message_count
    
    # ================================================================
    # Finance
    # ================================================================
    
    async def _generate_budgets(self) -> int:
        """Generate budgets."""
        budget_types = ["operating", "capital", "project", "department", "marketing", "engineering"]
        statuses = ["active"] * 60 + ["draft"] * 20 + ["closed"] * 20
        
        project_ids = self._created_ids["projects"]
        department_ids = self._created_ids["departments"]
        
        count = max(1, self.config.dept_count * 2)
        
        for i in range(count):
            budget = Budget(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Budget {i+1}: {self.rng.choice(budget_types).title()} Budget {self.rng.choice(['Q1', 'Q2', 'Q3', 'Q4', 'FY'])}",
                budget_type=self.rng.choice(budget_types),
                status=self.rng.choice(statuses),
                allocated_amount=round(self.rng.uniform(10000, 1000000), 2),
                used_amount=round(self.rng.uniform(0, 500000), 2),
                currency="USD",
                project_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None,
                department_id=self.rng.choice(department_ids) if department_ids else None,
                period_start=utcnow().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
                period_end=utcnow().replace(month=12, day=31, hour=23, minute=59, second=59),
            )
            self.db.add(budget)
            self._created_ids["budgets"].append(budget.id)
        
        await self.db.flush()
        return count
    
    async def _generate_vendors(self) -> int:
        """Generate vendors."""
        vendor_types = ["software", "hardware", "service", "consulting", "cloud", "saas", "infrastructure"]
        statuses = ["active"] * 80 + ["pending"] * 10 + ["archived"] * 10
        
        for i in range(self.config.vendor_count):
            vendor = Vendor(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Vendor {i+1}: {self.rng.choice(['AWS', 'Google Cloud', 'Azure', 'GitHub', 'Atlassian', 'Datadog', 'Snowflake', 'Stripe', 'Twilio', 'SendGrid'])}",
                kind=self.rng.choice(vendor_types),
                status=self.rng.choice(statuses),
                email=f"vendor{i+1}@example.com",
                contact_name=f"Contact {i+1}",
                country=self.rng.choice(["US", "UK", "DE", "FR", "CA", "AU", "JP", "SG"]),
                website=f"https://vendor{i+1}.example.com",
            )
            self.db.add(vendor)
            self._created_ids["vendors"].append(vendor.id)
        
        await self.db.flush()
        return self.config.vendor_count
    
    async def _generate_invoices(self) -> int:
        """Generate invoices."""
        count = max(1, self.config.vendor_count * 5)
        directions = ["inbound", "outbound"]
        statuses = ["paid"] * 60 + ["pending"] * 20 + ["overdue"] * 10 + ["cancelled"] * 10
        
        vendor_ids = self._created_ids["vendors"]
        
        for i in range(count):
            invoice = Invoice(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                vendor_id=self.rng.choice(vendor_ids) if vendor_ids else None,
                title=f"Invoice {i+1}",
                invoice_number=f"INV-{20240000 + i}",
                direction=self.rng.choice(directions),
                status=self.rng.choice(statuses),
                amount=round(self.rng.uniform(100, 50000), 2),
                currency="USD",
                issued_at=(utcnow() - timedelta(days=self.rng.randint(0, 365))).date(),
                due_at=(utcnow() + timedelta(days=self.rng.randint(0, 90))).date(),
            )
            self.db.add(invoice)
            self._created_ids["invoices"].append(invoice.id)
        
        await self.db.flush()
        return count
    
    async def _generate_purchase_orders(self) -> int:
        """Generate purchase orders."""
        count = max(1, self.config.vendor_count * 3)
        statuses = ["draft"] * 10 + ["sent"] * 20 + ["confirmed"] * 40 + ["received"] * 20 + ["cancelled"] * 10
        
        vendor_ids = self._created_ids["vendors"]
        
        for i in range(count):
            po = PurchaseOrder(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                vendor_id=self.rng.choice(vendor_ids) if vendor_ids else None,
                title=f"PO {i+1}: {self.rng.choice(['Software License', 'Hardware', 'Consulting', 'Cloud Credits', 'Support'])}",
                po_number=f"PO-{20240000 + i}",
                status=self.rng.choice(statuses),
                total_amount=round(self.rng.uniform(1000, 200000), 2),
                currency="USD",
                issued_at=utcnow() - timedelta(days=self.rng.randint(0, 365)),
                expected_delivery_at=(utcnow() + timedelta(days=self.rng.randint(0, 60))).date(),
            )
            self.db.add(po)
            self._created_ids["purchase_orders"].append(po.id)
        
        await self.db.flush()
        return count
    
    async def _generate_purchase_requests(self) -> int:
        """Generate purchase requests."""
        count = max(1, self.config.employee_count // 20)
        statuses = ["draft"] * 20 + ["submitted"] * 30 + ["approved"] * 30 + ["rejected"] * 10 + ["ordered"] * 10
        
        employee_ids = self._created_ids["employees"]
        vendor_ids = self._created_ids["vendors"]
        
        for i in range(count):
            pr = PurchaseRequest(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_id=self.rng.choice(employee_ids) if employee_ids else None,
                vendor_id=self.rng.choice(vendor_ids) if vendor_ids and self.rng.random() < 0.5 else None,
                title=f"PR {i+1}: {self.rng.choice(['New Laptop', 'Software License', 'Cloud Credits', 'Training', 'Conference', 'Equipment'])}",
                description=f"Purchase request {i+1} description",
                status=self.rng.choice(statuses),
                estimated_cost=round(self.rng.uniform(100, 10000), 2),
                currency="USD",
                category=self.rng.choice(["laptop", "monitor", "software", "furniture", "services", "cloud", "training", "equipment", "marketing", "other"]),
            )
            self.db.add(pr)
            self._created_ids["purchase_requests"].append(pr.id)
        
        await self.db.flush()
        return count
    
    async def _generate_expenses(self) -> int:
        """Generate expenses."""
        count = max(1, self.config.employee_count * 2)
        expense_types = ["travel", "food", "office", "software", "hardware", "training", "marketing", "client", "cloud", "miscellaneous"]
        statuses = ["submitted"] * 30 + ["approved"] * 50 + ["rejected"] * 10 + ["reimbursed"] * 10
        
        employee_ids = self._created_ids["employees"]
        
        for i in range(count):
            expense = Expense(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_id=self.rng.choice(employee_ids) if employee_ids else None,
                expense_type=self.rng.choice(expense_types),
                amount=round(self.rng.uniform(10, 5000), 2),
                currency="USD",
                incurred_at=(utcnow() - timedelta(days=self.rng.randint(0, 365))).date(),
                description=f"Expense {i+1}: {self.rng.choice(['Flight', 'Hotel', 'Meal', 'Software', 'Book', 'Course', 'Supplies'])}",
                status=self.rng.choice(statuses),
            )
            self.db.add(expense)
            self._created_ids["expenses"].append(expense.id)
        
        await self.db.flush()
        return count
    
    # ================================================================
    # Customers
    # ================================================================
    
    async def _generate_customers(self) -> int:
        """Generate customers."""
        industries = ["Technology", "Finance", "Healthcare", "Retail", "Manufacturing", "Education", "Government", "Media"]
        statuses = ["active"] * 70 + ["prospect"] * 15 + ["churned"] * 10 + ["onboarding"] * 5
        health = ["healthy"] * 50 + ["at_risk"] * 30 + ["critical"] * 10 + ["unknown"] * 10
        
        for i in range(self.config.customer_count):
            customer = Customer(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                company_name=f"Customer {i+1} {self.rng.choice(['Inc', 'LLC', 'Corp', 'Ltd', 'GmbH'])}",
                industry=self.rng.choice(industries),
                status=self.rng.choice(statuses),
                health_status=self.rng.choice(health),
                country=self.rng.choice(["US", "UK", "DE", "FR", "CA", "AU", "JP", "SG"]),
                website=f"https://customer{i+1}.example.com",
                description=f"Customer {i+1} description",
            )
            self.db.add(customer)
            self._created_ids["customers"].append(customer.id)
        
        await self.db.flush()
        return self.config.customer_count
    
    # ================================================================
    # Integrations
    # ================================================================
    
    async def _generate_integrations(self) -> int:
        """Generate integration connections."""
        providers = ["github", "gitlab", "slack", "teams", "jira", "linear", "asana", "notion", "salesforce", "hubspot"]
        statuses = ["connected"] * 70 + ["disconnected"] * 20 + ["error"] * 10
        
        for i in range(self.config.integration_count):
            provider = self.rng.choice(providers)
            conn = ConnectorInstance(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                connector_id=provider,
                name=f"{provider.title()} Integration {i+1}",
                config={"api_key": "***", "webhook_url": f"https://webhook{i+1}.example.com"},
                state=self.rng.choice(statuses),
                last_sync_at=utcnow() - timedelta(hours=self.rng.randint(0, 168)) if self.rng.random() < 0.8 else None,
                # sync_frequency_minutes is not a field on ConnectorInstance
            )
            self.db.add(conn)
            self._created_ids["integrations"].append(conn.id)
        
        await self.db.flush()
        
        # Generate sync runs
        sync_count = self.config.integration_count * 50
        for i in range(sync_count):
            conn_id = self.rng.choice(self._created_ids["integrations"])
            sync = SyncRun(
                id=uuid.uuid4().hex[:32],
                connector_instance_id=conn_id,
                organization_id=self.org_id,
                sync_mode=self.rng.choice(["full", "incremental"]),
                triggered_by=self.rng.choice(["scheduled", "manual", "webhook"]),
                trigger_id=None,
                state=self.rng.choice(["completed", "completed", "completed", "failed", "running"]),
                entities_processed=self.rng.randint(0, 1000),
                started_at=utcnow() - timedelta(days=self.rng.randint(0, 90), hours=self.rng.randint(0, 23)),
                completed_at=utcnow() - timedelta(days=self.rng.randint(0, 90), hours=self.rng.randint(0, 23)),
            )
            self.db.add(sync)
            self._created_ids["sync_runs"].append(sync.id)
        
        await self.db.flush()
        return self.config.integration_count
    
    # ================================================================
    # Security
    # ================================================================
    
    async def _generate_security_events(self) -> int:
        """Generate security events."""
        event_types = [
            "failed_login", "failed_login_brute_force", "successful_login_new_device",
            "password_reset", "mfa_enabled", "mfa_disabled", "role_changed",
            "permission_escalation", "data_export", "unusual_access_pattern",
            "api_key_created", "api_key_revoked", "webhook_created", "integration_modified"
        ]
        severities = ["low"] * 50 + ["medium"] * 30 + ["high"] * 15 + ["critical"] * 5
        statuses = ["open"] * 30 + ["investigating"] * 20 + ["resolved"] * 40 + ["false_positive"] * 10
        
        employee_ids = self._created_ids["employees"]
        
        for i in range(self.config.security_event_count):
            days_ago = self.rng.randint(0, 365 * self.config.years_of_history)
            
            event = SecurityEvent(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                event_type=self.rng.choice(event_types),
                severity=self.rng.choice(severities),
                title=f"Security Event {i+1}: {self.rng.choice(event_types).replace('_', ' ').title()}",
                actor_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.7 else None,
                source_ip=f"{self.rng.randint(1,255)}.{self.rng.randint(1,255)}.{self.rng.randint(1,255)}.{self.rng.randint(1,255)}",
                details=json.dumps({"attempts": self.rng.randint(1, 100), "duration_seconds": self.rng.randint(60, 3600)}),
                status=self.rng.choice(statuses),
                created_at=utcnow() - timedelta(days=days_ago, hours=self.rng.randint(0, 23)),
            )
            self.db.add(event)
            self._created_ids["security_events"].append(event.id)
        
        await self.db.flush()
        return self.config.security_event_count
    
    # ================================================================
    # Operations
    # ================================================================
    
    async def _generate_operations(self) -> int:
        """Generate canonical operations."""
        op_types = ["api_call", "webhook", "sync", "batch_job", "report", "export", "import", "migration"]
        states = ["completed"] * 70 + ["failed"] * 10 + ["unknown"] * 5 + ["retrying"] * 10 + ["queued"] * 5
        
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        
        count = max(1, self.config.employee_count * 5)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:op:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            op = CanonicalOperation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                operation_type=self.rng.choice(op_types),
                title=f"Operation {i+1}: {self.rng.choice(op_types).replace('_', ' ').title()}",
                description=f"Operation {i+1} description",
                scope_type="project" if project_ids and self.rng.random() < 0.5 else "company",
                scope_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.5 else None,
                actor_id=self.rng.choice(employee_ids) if employee_ids else None,
                actor_type="human",
                is_external=self.rng.random() < 0.2,
                external_system=self.rng.choice(["github", "slack", "jira", "salesforce"]) if self.rng.random() < 0.2 else None,
                state=self.rng.choice(states),
                current_attempt=self.rng.randint(1, 3),
                max_attempts=3,
                retry_policy="exponential_backoff",
                fingerprint=fingerprint,
            )
            self.db.add(op)
            self._created_ids["operations"].append(op.id)
        
        await self.db.flush()
        
        # Generate attempts for operations
        for op_id in self._created_ids["operations"]:
            attempt_count = self.rng.randint(1, 3)
            for a in range(attempt_count):
                fingerprint = hashlib.sha256(
                    f"{self.org_id}:attempt:{op_id}:{a}:{self.rng.random()}".encode()
                ).hexdigest()[:160]
                attempt = OperationAttempt(
                    id=uuid.uuid4().hex[:32],
                    operation_id=op_id,
                    organization_id=self.org_id,
                    attempt_number=a + 1,
                    state=self.rng.choice(["completed", "completed", "failed", "executing"]),
                    worker_id="worker-1",
                    worker_instance="instance-1",
                    started_at=utcnow() - timedelta(days=self.rng.randint(0, 30)),
                    completed_at=utcnow() - timedelta(days=self.rng.randint(0, 30), hours=-1),
                    outcome=self.rng.choice(["success", "success", "failure", "timeout"]),
                    duration_ms=self.rng.randint(100, 300000),
                    fingerprint=fingerprint,
                )
                self.db.add(attempt)
        
        await self.db.flush()
        return count
    
    # ================================================================
    # Observability
    # ================================================================
    
    async def _generate_observations(self) -> int:
        """Generate canonical observations."""
        obs_types = [
            "request", "worker_execution", "operation_lifecycle", "integration_sync",
            "external_operation", "security_event", "recovery_action", "reconciliation",
            "health_check", "freshness_check", "slo_evaluation", "attention_signal",
            "degradation", "correlation"
        ]
        sources = ["api", "worker", "integration", "database", "cache", "queue", "scheduler", "webhook"]
        severities = ["debug"] * 30 + ["info"] * 40 + ["notice"] * 15 + ["warning"] * 10 + ["critical"] * 5
        
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        task_ids = self._created_ids["tasks"]
        integration_ids = self._created_ids["integrations"]
        
        for i in range(self.config.observation_count):
            days_ago = self.rng.randint(0, 365 * self.config.years_of_history)
            
            fingerprint = hashlib.sha256(
                f"{self.org_id}:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            obs = CanonicalObservation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                observation_type=self.rng.choice(obs_types),
                source=self.rng.choice(sources),
                source_component=f"{self.rng.choice(sources)}-{self.rng.randint(1, 10)}",
                actor_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.3 else None,
                actor_type="system",
                severity=self.rng.choice(severities),
                epistemic_status="observed",
                correlation_id=uuid.uuid4().hex[:32] if self.rng.random() < 0.3 else None,
                trace_id=uuid.uuid4().hex[:32] if self.rng.random() < 0.2 else None,
                operation_id=self.rng.choice(self._created_ids["operations"]) if self._created_ids["operations"] and self.rng.random() < 0.2 else None,
                integration_id=self.rng.choice(integration_ids) if integration_ids and self.rng.random() < 0.2 else None,
                title=f"Observation {i+1}",
                description=f"Observation {i+1} description",
                details_json=json.dumps({"key": f"value_{i}", "metric": self.rng.uniform(0, 100)}),
                metrics_json=json.dumps({"duration_ms": self.rng.randint(1, 5000), "count": self.rng.randint(1, 100)}),
                observed_at=utcnow() - timedelta(days=days_ago, hours=self.rng.randint(0, 23)),
                duration_ms=self.rng.randint(1, 5000),
                fingerprint=fingerprint,
            )
            self.db.add(obs)
            self._created_ids["observations"].append(obs.id)
        
        await self.db.flush()
        return self.config.observation_count
    
    async def _generate_correlations(self) -> int:
        """Generate correlation contexts."""
        corr_types = ["request_flow", "error_trace", "deployment", "incident", "business_transaction"]
        statuses = ["active"] * 30 + ["completed"] * 60 + ["failed"] * 10
        
        count = max(1, self.config.employee_count // 10)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:corr:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            chain = {
                "steps": [
                    {"step_number": 1, "observation_type": "request", "source": "api", "outcome": "success"},
                    {"step_number": 2, "observation_type": "processing", "source": "worker", "outcome": "success"},
                    {"step_number": 3, "observation_type": "response", "source": "api", "outcome": "success"},
                ]
            }
            
            ctx = CorrelationContext(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                correlation_type=self.rng.choice(corr_types),
                correlation_id=uuid.uuid4().hex[:32],
                trace_id=uuid.uuid4().hex[:32],
                chain_json=json.dumps(chain),
                current_step=3,
                total_steps=3,
                status=self.rng.choice(statuses),
                outcome="success",
                fingerprint=fingerprint,
            )
            self.db.add(ctx)
            self._created_ids["correlations"].append(ctx.id)
        
        await self.db.flush()
        return count
    
    async def _generate_degradations(self) -> int:
        """Generate degradations."""
        deg_types = ["performance", "availability", "data_quality", "integration", "capacity", "security"]
        severities = ["minor"] * 50 + ["major"] * 35 + ["critical"] * 15
        states = ["detected"] * 10 + ["investigating"] * 20 + ["contained"] * 20 + ["recovering"] * 20 + ["verified"] * 20 + ["learned"] * 10
        
        count = max(1, self.config.employee_count // 100)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:deg:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            deg = Degradation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                degradation_type=self.rng.choice(deg_types),
                severity=self.rng.choice(severities),
                title=f"Degradation {i+1}: {self.rng.choice(deg_types).title()} Issue",
                description=f"Degradation {i+1} description",
                state=self.rng.choice(states),
                details_json=json.dumps({"impact": "medium", "affected_services": ["api", "worker"]}),
                affected_entities_json=json.dumps([{"type": "service", "id": "api-1"}]),
                affected_dimensions_json=json.dumps(["latency", "availability"]),
                detected_at=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)),
                acknowledged_at=utcnow() - timedelta(days=self.rng.randint(0, 30)) if self.rng.random() < 0.8 else None,
                fingerprint=fingerprint,
            )
            self.db.add(deg)
            self._created_ids["degradations"].append(deg.id)
        
        await self.db.flush()
        return count
    
    async def _generate_health_dimensions(self) -> int:
        """Generate health dimensions."""
        dimensions = [
            "latency_p99", "error_rate", "throughput", "availability", "cpu_utilization",
            "memory_utilization", "disk_utilization", "queue_depth", "cache_hit_rate",
            "deployment_frequency", "lead_time", "mttr", "change_failure_rate",
            "customer_satisfaction", "employee_satisfaction", "security_posture",
            "compliance_score", "cost_efficiency", "revenue_per_employee",
        ]
        
        scopes = ["company", "department", "team"]
        
        dept_ids = self._created_ids["departments"]
        team_ids = self._created_ids["teams"]
        
        # Create unique combinations
        created_combinations = set()
        
        for i in range(len(dimensions) * 3):  # Multiple snapshots per dimension
            dimension = self.rng.choice(dimensions)
            scope_type = self.rng.choice(scopes)
            
            if scope_type == "department" and dept_ids:
                scope_id = self.rng.choice(dept_ids)
            elif scope_type == "team" and team_ids:
                scope_id = self.rng.choice(team_ids)
            else:
                scope_id = None
            
            # Ensure unique combination
            combo = (dimension, scope_type, scope_id)
            if combo in created_combinations:
                continue
            created_combinations.add(combo)
            
            fingerprint = hashlib.sha256(
                f"{self.org_id}:hdim:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            hdim = HealthDimension(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                dimension=dimension,
                scope_type=scope_type,
                scope_id=scope_id,
                status=self.rng.choice(["healthy", "healthy", "healthy", "degraded", "critical"]),
                current_value=self.rng.uniform(0, 100),
                target_value=self.rng.uniform(50, 95),
                threshold_warn=self.rng.uniform(60, 80),
                threshold_critical=self.rng.uniform(80, 95),
                unit=self.rng.choice(["ms", "%", "count", "ratio", "score"]),
                trend=self.rng.choice(["improving", "stable", "degrading", "volatile"]),
                trend_score=self.rng.uniform(-1, 1),
                slo_target=self.rng.uniform(90, 99.9),
                slo_compliance=self.rng.uniform(80, 100),
                recorded_at=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)),
                window_start=utcnow() - timedelta(days=7),
                window_end=utcnow(),
                fingerprint=fingerprint,
            )
            self.db.add(hdim)
            self._created_ids["health_dimensions"].append(hdim.id)
        
        await self.db.flush()
        return len(created_combinations)
    
    async def _generate_slo_targets(self) -> int:
        """Generate SLO targets."""
        dimensions = ["latency_p99", "error_rate", "availability", "throughput"]
        
        for dim in dimensions:
            fingerprint = hashlib.sha256(
                f"{self.org_id}:slo:{dim}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            slo = SLOTarget(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                dimension=dim,
                scope_type="company",
                target_value=self.rng.uniform(95, 99.9) if dim != "error_rate" else self.rng.uniform(0.01, 0.1),
                operator="<=" if dim == "error_rate" else ">=",
                unit="%" if dim != "latency_p99" else "ms",
                window_type="rolling",
                window_size="30d",
                status="active",
                current_compliance=self.rng.uniform(80, 100),
                fingerprint=fingerprint,
            )
            self.db.add(slo)
            self._created_ids["slo_targets"].append(slo.id)
        
        await self.db.flush()
        return len(dimensions)
    
    async def _generate_freshness_checks(self) -> int:
        """Generate freshness checks."""
        feed_types = ["integration", "worker", "database", "cache", "queue", "external_api"]
        statuses = ["fresh"] * 60 + ["delayed"] * 25 + ["stale"] * 10 + ["unknown"] * 5
        
        integration_ids = self._created_ids["integrations"]
        
        count = max(1, self.config.integration_count * 2 + self.config.employee_count // 100)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:fresh:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            fresh = FreshnessCheck(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                feed_type=self.rng.choice(feed_types),
                scope_type="integration" if self.rng.random() < 0.5 else "worker",
                scope_id=self.rng.choice(integration_ids) if integration_ids and self.rng.random() < 0.5 else None,
                feed_id=f"feed_{i}",
                status=self.rng.choice(statuses),
                expected_interval_seconds=self.rng.choice([60, 300, 600, 1800, 3600]),
                last_event_at=utcnow() - timedelta(seconds=self.rng.randint(0, 86400)),
                delay_seconds=self.rng.randint(0, 86400),
                max_acceptable_delay_seconds=self.rng.choice([3600, 7200, 14400, 86400]),
                fingerprint=fingerprint,
            )
            self.db.add(fresh)
            self._created_ids["freshness_checks"].append(fresh.id)
        
        await self.db.flush()
        return count
    
    async def _generate_operational_targets(self) -> int:
        """Generate operational targets."""
        target_types = ["deployment_time", "incident_response", "recovery_time", "build_time", "test_time"]
        
        for ttype in target_types:
            fingerprint = hashlib.sha256(
                f"{self.org_id}:otarget:{ttype}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            target = OperationalTarget(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                target_type=ttype,
                scope_type="company",
                target_duration_seconds=self.rng.randint(300, 3600),
                target_value=self.rng.uniform(0.8, 0.99),
                unit="ratio",
                status=self.rng.choice(["active", "met", "missed"]),
                fingerprint=fingerprint,
            )
            self.db.add(target)
            self._created_ids["operational_targets"].append(target.id)
        
        await self.db.flush()
        return len(target_types)
    
    # ================================================================
    # Learning
    # ================================================================
    
    async def _generate_learning(self) -> int:
        """Generate organizational learning entries."""
        kinds = ["pattern", "anti_pattern", "decision_principle", "process_improvement", "technical_guidance"]
        statuses = ["active"] * 60 + ["superseded"] * 20 + ["archived"] * 20
        lifecycles = ["observed"] * 30 + ["validated"] * 40 + ["institutionalized"] * 30
        
        count = max(1, self.config.employee_count // 20)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:learning:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            learning = OrganizationalLearning(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                kind=self.rng.choice(kinds),
                fingerprint=fingerprint,
                title=f"Lesson {i+1}: {self.rng.choice(['Always', 'Never', 'Prefer', 'Avoid', 'Consider'])} {self.rng.choice(['validate input', 'use transactions', 'add indexes', 'monitor latency', 'test edge cases'])}",
                lesson=f"Detailed lesson {i+1}: Based on {self.rng.randint(1, 50)} observations, we learned that...",
                status=self.rng.choice(statuses),
                lifecycle=self.rng.choice(lifecycles),
                confidence=self.rng.uniform(0.5, 0.95),
                topic_name=self.rng.choice(["engineering", "process", "security", "performance", "reliability"]),
                source_type="pattern",
                source_id=None,
                observed_at=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)),
            )
            self.db.add(learning)
            self._created_ids["learning"].append(learning.id)
        
        await self.db.flush()
        return count
    
    # ================================================================
    # Attention
    # ================================================================
    
    async def _generate_attention(self) -> int:
        """Generate company attention signals."""
        attn_types = ["degradation", "freshness_stale", "security", "capacity", "slo_breach", "drift", "learning"]
        priorities = ["info"] * 40 + ["watch"] * 30 + ["alert"] * 20 + ["critical"] * 10
        urgencies = ["low"] * 30 + ["normal"] * 40 + ["high"] * 20 + ["critical"] * 10
        statuses = ["open"] * 50 + ["acknowledged"] * 20 + ["in_progress"] * 15 + ["resolved"] * 15
        
        count = max(1, self.config.employee_count // 50)
        
        for i in range(count):
            attn = CompanyAttention(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                attention_type=self.rng.choice(attn_types),
                priority=self.rng.choice(priorities),
                title=f"Attention {i+1}: {self.rng.choice(attn_types).replace('_', ' ').title()}",
                description=f"Attention signal {i+1} description",
                source_type="system",
                source_id=str(i),
                priority_score=self.rng.uniform(0, 1),
                urgency=self.rng.choice(urgencies),
                status=self.rng.choice(statuses),
                assigned_to=self.rng.choice(self._created_ids["employees"]) if self._created_ids["employees"] and self.rng.random() < 0.5 else None,
            )
            self.db.add(attn)
            self._created_ids["attention"].append(attn.id)
        
        await self.db.flush()
        return count


# ================================================================
# Scale Test Runner
# ================================================================

async def run_scale_generation(
    db: AsyncSession,
    organization_id: str,
    scale: str = "medium",
) -> Dict[str, int]:
    """Run scale data generation for a given scale level."""
    if scale not in SCALE_LEVELS:
        raise ValueError(f"Unknown scale: {scale}. Valid: {list(SCALE_LEVELS.keys())}")
    
    config = ScaleConfig(
        name=scale,
        employee_count=SCALE_LEVELS[scale],
    )
    
    generator = ScaleGenerator(db, organization_id, config)
    return await generator.generate_all()


async def run_all_scales(
    db: AsyncSession,
    base_org_id: str,
) -> Dict[str, Dict[str, int]]:
    """Run generation for all scale levels (creates separate orgs)."""
    results = {}
    
    for scale_name, emp_count in SCALE_LEVELS.items():
        # Create org for this scale
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name=f"Scale Test {scale_name.title()} ({emp_count} employees)",
            slug=f"scale-{scale_name}-{emp_count}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            status="active",
        )
        db.add(org)
        await db.flush()
        
        config = ScaleConfig(name=scale_name, employee_count=emp_count)
        generator = ScaleGenerator(db, org.id, config)
        results[scale_name] = await generator.generate_all()
        
        await db.commit()
    
    return results


def get_scale_config(scale: str) -> ScaleConfig:
    """Get scale configuration by name."""
    if scale not in SCALE_LEVELS:
        raise ValueError(f"Unknown scale: {scale}")
    return ScaleConfig(name=scale, employee_count=SCALE_LEVELS[scale])


# ================================================================
# SYNCHRONOUS SCALE GENERATOR
# Uses sync SQLAlchemy session to avoid asyncpg concurrency issues.
# ================================================================

import time
import hashlib
from contextlib import contextmanager
from typing import Generator as TypingGenerator, Optional, List, Dict, Any
from datetime import datetime

from tests.scale.scale_state import (
    ScaleRunCheckpoint,
    ScaleRunPhase,
    ScaleRunStateStore,
    ScaleRunMetadata,
)


@contextmanager
def timed_section(name: str, timings: Dict[str, float]) -> TypingGenerator[None, None, None]:
    """Context manager for timing code sections."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        timings[name] = timings.get(name, 0.0) + elapsed


class SyncScaleGenerator:
    """Generates realistic company data at scale using canonical models (sync version).
    
    Uses a synchronous SQLAlchemy session to avoid asyncpg greenlet concurrency issues.
    Includes timing instrumentation for bottleneck identification.
    Supports both ScaleConfig (legacy) and UniversalScaleProfile (35-F).
    """
    
    def __init__(self, db, organization_id: str, config, 
                 run_metadata: Optional[ScaleRunMetadata] = None,
                 state_store: Optional[ScaleRunStateStore] = None):
        self.db = db
        self.org_id = organization_id
        # Support both ScaleConfig (legacy) and UniversalScaleProfile (35-F)
        if isinstance(config, ScaleConfig):
            self.profile = UniversalScaleProfile.from_scale_config(config)
        else:
            self.profile = config
        self.config = self.profile  # Backward compatibility alias
        self.rng = random.Random(42)  # Deterministic seed
        self._created_ids: Dict[str, List[str]] = defaultdict(list)
        self._id_maps: Dict[str, Dict[str, Any]] = {}
        self._timings: Dict[str, float] = {}
        self._closed = False
        
        # Checkpointing support
        self._run_metadata = run_metadata
        self._state_store = state_store
        self._current_phase: Optional[ScaleRunPhase] = None
        self._batch_counter: Dict[str, int] = defaultdict(int)
    
    def close(self) -> None:
        """Explicitly close and clean up generator resources.
        
        Ensures all database resources are properly released.
        Idempotent - safe to call multiple times.
        """
        if self._closed:
            return
        
        try:
            # Flush any pending changes
            if self.db is not None:
                self.db.flush()
        except Exception:
            pass
        
        try:
            # Close the session if we own it
            if self.db is not None:
                self.db.close()
        except Exception:
            pass
        
        self._closed = True
    
    def __enter__(self):
        """Context manager entry."""
        # Disable autovacuum during generation to prevent crashes
        self._disable_autovacuum()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        # Re-enable autovacuum
        self._enable_autovacuum()
        # Run ANALYZE to update statistics for query planner
        self._analyze_tables()
        self.close()
        return False  # Don't suppress exceptions
    
    def _disable_autovacuum(self) -> None:
        """Disable autovacuum during generation to prevent crashes."""
        try:
            self.db.execute(text("ALTER SYSTEM SET autovacuum = off"))
            self.db.execute(text("SELECT pg_reload_conf()"))
        except Exception:
            pass
    
    def _enable_autovacuum(self) -> None:
        """Re-enable autovacuum after generation."""
        try:
            self.db.execute(text("ALTER SYSTEM SET autovacuum = on"))
            self.db.execute(text("SELECT pg_reload_conf()"))
        except Exception:
            pass
    
    def _analyze_tables(self) -> None:
        """Run ANALYZE to update statistics for query planner."""
        try:
            self.db.execute(text("ANALYZE"))
        except Exception:
            pass
    
    # ================================================================
    # CHECKPOINTING SUPPORT
    # ================================================================
    
    def _start_phase(self, phase: ScaleRunPhase) -> None:
        """Start a generation phase and record checkpoint."""
        self._current_phase = phase
        if self._run_metadata and self._state_store:
            self._run_metadata.current_phase = phase
            self._state_store.save(self._run_metadata)
    
    def _record_checkpoint(
        self,
        entity_type: str,
        batch_number: int,
        rows_created: int,
        rows_expected: int,
        fingerprint: Optional[str] = None,
    ) -> None:
        """Record a generation checkpoint for resumability."""
        if not self._run_metadata or not self._state_store:
            return
        
        checkpoint = ScaleRunCheckpoint(
            run_id=self._run_metadata.run_id,
            phase=self._current_phase or ScaleRunPhase.GENERATION,
            entity_type=entity_type,
            batch_number=batch_number,
            rows_created=rows_created,
            rows_expected=rows_expected,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            fingerprint=fingerprint,
        )
        self._run_metadata.add_checkpoint(checkpoint)
        self._state_store.save(self._run_metadata)
    
    def _get_checkpoint_state(self, entity_type: str) -> Dict[str, Any]:
        """Get the checkpoint state for an entity type."""
        if not self._run_metadata:
            return {"batch": 0, "completed": False}
        
        checkpoints = [
            c for c in self._run_metadata.checkpoints 
            if c.entity_type == entity_type and c.completed_at is not None
        ]
        
        if checkpoints:
            latest = max(checkpoints, key=lambda c: c.batch_number)
            return {
                "batch": latest.batch_number,
                "completed": latest.rows_created >= latest.rows_expected,
                "rows_created": latest.rows_created,
                "rows_expected": latest.rows_expected,
            }
        return {"batch": 0, "completed": False}
    
    def _can_skip_entity_type(self, entity_type: str, expected_rows: int) -> bool:
        """Check if entity type generation can be skipped (already completed)."""
        state = self._get_checkpoint_state(entity_type)
        return state["completed"] and state["rows_created"] >= expected_rows
    
    def _get_next_batch(self, entity_type: str) -> int:
        """Get the next batch number for an entity type."""
        state = self._get_checkpoint_state(entity_type)
        return state["batch"] + 1
    
    def generate_all(self) -> Dict[str, int]:
        """Generate complete company reality at scale (sync) with timing instrumentation and checkpointing."""
        counts = {}
        total_start = time.perf_counter()
        
        # Start generation phase
        self._start_phase(ScaleRunPhase.GENERATION)
        
        # Core org structure
        self._start_phase(ScaleRunPhase.GENERATION)
        
        with timed_section("generate_roles", self._timings):
            counts["roles"] = self._generate_roles()
        with timed_section("flush_roles", self._timings):
            self.db.flush()
            self._record_checkpoint("roles", 1, counts["roles"], self.profile.role_count)
        
        with timed_section("generate_departments", self._timings):
            counts["departments"] = self._generate_departments()
        with timed_section("flush_departments", self._timings):
            self.db.flush()
            self._record_checkpoint("departments", 1, counts["departments"], self.profile.dept_count)
        
        with timed_section("generate_teams", self._timings):
            counts["teams"] = self._generate_teams()
        with timed_section("flush_teams", self._timings):
            self.db.flush()
            self._record_checkpoint("teams", 1, counts["teams"], self.profile.team_count)
        
        with timed_section("generate_employees", self._timings):
            counts["employees"] = self._generate_employees()
        with timed_section("flush_employees", self._timings):
            self.db.flush()
            self._record_checkpoint("employees", 1, counts["employees"], self.profile.employee_count)
        
        with timed_section("generate_user_roles", self._timings):
            counts["user_roles"] = self._generate_user_roles()
        with timed_section("flush_user_roles", self._timings):
            self.db.flush()
            self._record_checkpoint("user_roles", 1, counts["user_roles"], self.profile.employee_count)
        
        # Work structure
        with timed_section("generate_projects", self._timings):
            counts["projects"] = self._generate_projects()
        with timed_section("flush_projects", self._timings):
            self.db.flush()
            self._record_checkpoint("projects", 1, counts["projects"], self.profile.project_count)
        
        with timed_section("generate_tasks", self._timings):
            counts["tasks"] = self._generate_tasks()
        self._record_checkpoint("tasks", 1, counts["tasks"], self.profile.task_count)
        
        with timed_section("generate_goals", self._timings):
            counts["goals"] = self._generate_goals()
        self._record_checkpoint("goals", 1, counts["goals"], self.profile.goal_count)
        
        with timed_section("generate_meetings", self._timings):
            counts["meetings"] = self._generate_meetings()
        self._record_checkpoint("meetings", 1, counts["meetings"], self.profile.meeting_count)
        
        with timed_section("generate_decisions", self._timings):
            counts["decisions"] = self._generate_decisions()
        self._record_checkpoint("decisions", 1, counts["decisions"], self.profile.decision_count)
        
        # Knowledge
        with timed_section("generate_documents", self._timings):
            counts["documents"] = self._generate_documents()
        self._record_checkpoint("documents", 1, counts["documents"], self.profile.document_count)
        
        with timed_section("generate_wiki_pages", self._timings):
            counts["wiki_pages"] = self._generate_wiki_pages()
        self._record_checkpoint("wiki_pages", 1, counts["wiki_pages"], self.profile.wiki_page_count)
        
        with timed_section("generate_policies", self._timings):
            counts["policies"] = self._generate_policies()
        self._record_checkpoint("policies", 1, counts["policies"], self.profile.policy_count)
        
        with timed_section("generate_sops", self._timings):
            counts["sops"] = self._generate_sops()
        self._record_checkpoint("sops", 1, counts["sops"], self.profile.sop_count)
        
        with timed_section("generate_templates", self._timings):
            counts["templates"] = self._generate_templates()
        self._record_checkpoint("templates", 1, counts["templates"], self.profile.template_count)
        
        # Communication
        with timed_section("generate_conversations", self._timings):
            counts["conversations"] = self._generate_conversations()
        self._record_checkpoint("conversations", 1, counts["conversations"], self.profile.conversation_count)
        
        with timed_section("generate_messages", self._timings):
            counts["messages"] = self._generate_messages()
        self._record_checkpoint("messages", 1, counts["messages"], self.profile.message_count)
        
        # Finance
        with timed_section("generate_budgets", self._timings):
            counts["budgets"] = self._generate_budgets()
        self._record_checkpoint("budgets", 1, counts["budgets"], self.profile.budget_count)
        
        with timed_section("generate_vendors", self._timings):
            counts["vendors"] = self._generate_vendors()
        self._record_checkpoint("vendors", 1, counts["vendors"], self.profile.vendor_count)
        
        with timed_section("flush_vendors", self._timings):
            self.db.flush()
        
        with timed_section("generate_invoices", self._timings):
            counts["invoices"] = self._generate_invoices()
        self._record_checkpoint("invoices", 1, counts["invoices"], self.profile.invoice_count)
        
        with timed_section("generate_purchase_orders", self._timings):
            counts["purchase_orders"] = self._generate_purchase_orders()
        self._record_checkpoint("purchase_orders", 1, counts["purchase_orders"], self.profile.purchase_order_count)
        
        with timed_section("generate_purchase_requests", self._timings):
            counts["purchase_requests"] = self._generate_purchase_requests()
        self._record_checkpoint("purchase_requests", 1, counts["purchase_requests"], self.profile.purchase_request_count)
        
        with timed_section("generate_expenses", self._timings):
            counts["expenses"] = self._generate_expenses()
        self._record_checkpoint("expenses", 1, counts["expenses"], self.profile.expense_count)
        
        # Customers
        with timed_section("generate_customers", self._timings):
            counts["customers"] = self._generate_customers()
        self._record_checkpoint("customers", 1, counts["customers"], self.profile.customer_count)
        
        # Integrations
        with timed_section("generate_integrations", self._timings):
            counts["integrations"] = self._generate_integrations()
        self._record_checkpoint("integrations", 1, counts["integrations"], self.profile.integration_count)
        
        # Security
        with timed_section("generate_security_events", self._timings):
            counts["security_events"] = self._generate_security_events()
        self._record_checkpoint("security_events", 1, counts["security_events"], self.profile.security_event_count)
        
        # Operations
        with timed_section("generate_operations", self._timings):
            counts["operations"] = self._generate_operations()
        self._record_checkpoint("operations", 1, counts["operations"], self.profile.operation_count)
        
        # Observability
        with timed_section("generate_observations", self._timings):
            counts["observations"] = self._generate_observations()
        self._record_checkpoint("observations", 1, counts["observations"], self.profile.observation_count)
        
        with timed_section("generate_correlations", self._timings):
            counts["correlations"] = self._generate_correlations()
        self._record_checkpoint("correlations", 1, counts["correlations"], self.profile.correlation_count)
        
        with timed_section("generate_degradations", self._timings):
            counts["degradations"] = self._generate_degradations()
        self._record_checkpoint("degradations", 1, counts["degradations"], self.profile.degradation_count)
        
        with timed_section("generate_health_dimensions", self._timings):
            counts["health_dimensions"] = self._generate_health_dimensions()
        self._record_checkpoint("health_dimensions", 1, counts["health_dimensions"], self.profile.health_dimension_count)
        
        with timed_section("generate_slo_targets", self._timings):
            counts["slo_targets"] = self._generate_slo_targets()
        self._record_checkpoint("slo_targets", 1, counts["slo_targets"], self.profile.slo_target_count)
        
        with timed_section("generate_freshness_checks", self._timings):
            counts["freshness_checks"] = self._generate_freshness_checks()
        self._record_checkpoint("freshness_checks", 1, counts["freshness_checks"], self.profile.freshness_check_count)
        
        with timed_section("generate_operational_targets", self._timings):
            counts["operational_targets"] = self._generate_operational_targets()
        self._record_checkpoint("operational_targets", 1, counts["operational_targets"], self.profile.operational_target_count)
        
        # Learning
        with timed_section("generate_learning", self._timings):
            counts["learning"] = self._generate_learning()
        self._record_checkpoint("learning", 1, counts["learning"], self.profile.learning_count)
        
        # Attention
        with timed_section("generate_attention", self._timings):
            counts["attention"] = self._generate_attention()
        self._record_checkpoint("attention", 1, counts["attention"], self.profile.attention_count)
        
        total_time = time.perf_counter() - total_start
        self._timings["total_generation_seconds"] = total_time
        
        # Record data generated checkpoint
        if self._run_metadata and self._state_store:
            self._run_metadata.current_phase = ScaleRunPhase.DATA_GENERATED
            self._state_store.save(self._run_metadata)
        
        return counts
    
    # Sync versions of all generation methods
    def _generate_roles(self) -> int:
        roles_data = [
            ("admin", "Administrator", "Full system access", True, True),
            ("employee", "Employee", "Standard employee access", True, True),
            ("manager", "Manager", "Team management access", True, False),
            ("hr", "Human Resources", "HR management access", True, False),
            ("finance", "Finance", "Financial management access", True, False),
            ("viewer", "Viewer", "Read-only access", True, False),
        ]
        
        for code, name, desc, is_system, is_default in roles_data:
            role = Role(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=name,
                code=code,
                description=desc,
                is_system=is_system,
                is_default=is_default,
            )
            self.db.add(role)
            self._created_ids["roles"].append(role.id)
            self._id_maps.setdefault("roles", {})[code] = role.id
        
        return len(roles_data)
    
    def _generate_departments(self) -> int:
        """Generate departments with hierarchical structure for large organizations."""
        dept_names = [
            "Engineering", "Product", "Design", "Sales", "Marketing",
            "Customer Success", "Finance", "HR", "Legal", "IT",
            "Security", "Operations", "Data", "Research", "Support",
        ]
        
        # For large orgs, create business units / divisions
        is_large_org = self.profile.employee_count >= 5000
        
        dept_configs = []
        if is_large_org:
            # Create division/business unit structure
            divisions = [
                ("Engineering Division", ["Platform Engineering", "Product Engineering", "Infrastructure", "Data Engineering", "ML Engineering", "Security Engineering"]),
                ("Product Division", ["Product Management", "Product Design", "User Research", "Product Operations"]),
                ("Go-to-Market Division", ["Sales", "Marketing", "Customer Success", "Sales Engineering", "Revenue Operations"]),
                ("Corporate Functions", ["Finance", "HR", "Legal", "IT", "Corporate Security", "Operations"]),
            ]
            for div_name, depts in divisions:
                dept_configs.append((div_name, True))  # Division
                for dept in depts:
                    dept_configs.append((dept, False))
        else:
            for name in dept_names:
                dept_configs.append((name, False))
        
        # Track used codes to ensure uniqueness
        used_codes = set()
        dept_ids = []  # Track created department IDs for parent references
        
        for i, (name, is_division) in enumerate(dept_configs[:self.config.dept_count]):
            # Generate unique code
            base_code = name[:3].upper()
            code = base_code
            counter = 1
            while code in used_codes:
                counter += 1
                code = f"{base_code}{counter}"
            used_codes.add(code)
            
            # For hierarchical structure, divisions can be parents of departments
            parent_id = None
            if not is_division and dept_ids and self.rng.random() < 0.3:
                # Some departments have a parent (division)
                parent_id = self.rng.choice(dept_ids)
            
            dept = Department(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=name,
                code=code,
                description=f"{name} {'division' if is_division else 'department'}",
                parent_id=parent_id,
                head_id=None,  # Will be set when employees are created
                location_id=None,
            )
            self.db.add(dept)
            dept_ids.append(dept.id)
            self._created_ids["departments"].append(dept.id)
            self._id_maps.setdefault("departments", {})[name] = dept.id
        
        return self.config.dept_count
    
    def _generate_teams(self) -> int:
        """Generate teams with support for matrix and project-based structures."""
        team_types = ["Platform", "Product", "Infrastructure", "Frontend", "Backend", 
                      "Mobile", "Data", "ML", "DevOps", "QA", "Security", "Growth"]
        
        dept_ids = self._created_ids["departments"]
        employee_ids = self._created_ids["employees"]
        
        is_large_org = self.profile.employee_count >= 5000
        
        team_counter = 0
        for dept_id in dept_ids:
            teams_per_dept = self.profile.team_per_dept
            if is_large_org:
                teams_per_dept = self.profile.team_per_dept * 2  # More teams in large orgs
            
            for j in range(teams_per_dept):
                team_type = self.rng.choice(team_types)
                team_counter += 1
                team = Team(
                    id=uuid.uuid4().hex[:32],
                    organization_id=self.org_id,
                    name=f"{team_type} Team {team_counter}",
                    code=f"{team_type[:3].upper()}{team_counter:02d}",
                    description=f"{team_type} team in department",
                    department_id=dept_id,
                    lead_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.7 else None,
                )
                self.db.add(team)
                self._created_ids["teams"].append(team.id)
                self._id_maps.setdefault("teams", {})[f"{dept_id}_{team_type}"] = team.id
        
        # For large orgs, add cross-functional project teams
        if is_large_org:
            project_team_count = max(1, self.profile.employee_count // 500)
            for i in range(project_team_count):
                team_counter += 1
                team = Team(
                    id=uuid.uuid4().hex[:32],
                    organization_id=self.org_id,
                    name=f"Project Team {team_counter}",
                    code=f"PRJ{team_counter:03d}",
                    description="Cross-functional project team",
                    department_id=self.rng.choice(dept_ids) if dept_ids else None,
                    lead_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.5 else None,
                )
                self.db.add(team)
                self._created_ids["teams"].append(team.id)
        
        return team_counter
    
    def _generate_employees(self) -> int:
        """Generate employees with realistic reporting hierarchy."""
        employee_ids = []
        dept_ids = self._created_ids["departments"]
        team_ids = self._created_ids["teams"]
        
        # Designations by level
        individual_contributor = [
            "Software Engineer", "Senior Software Engineer", "Staff Engineer",
            "Product Manager", "Designer", "Data Scientist", "DevOps Engineer",
            "QA Engineer", "Technical Writer", "Security Engineer",
        ]
        management = [
            "Engineering Manager", "Technical Lead", "Director of Engineering",
            "VP Engineering", "Product Director", "Director of Product",
            "Director of Design", "Sales Manager", "Marketing Director",
        ]
        executive = [
            "CTO", "CPO", "CFO", "COO", "CEO",
        ]
        
        employment_types = ["full_time"] * 85 + ["part_time"] * 10 + ["contractor"] * 5
        statuses = ["active"] * 90 + ["probation"] * 5 + ["notice"] * 3 + ["on_leave"] * 2
        
        is_large_org = self.profile.employee_count >= 5000
        
        # Create employees in order to establish hierarchy
        # First create executives (1-2)
        executive_count = min(3, max(1, self.profile.employee_count // 10000))
        for i in range(executive_count):
            dept_id = self.rng.choice(dept_ids) if dept_ids else None
            team_id = self.rng.choice(team_ids) if team_ids else None
            
            emp = Employee(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_number=f"E{i+1:05d}",
                first_name=f"Executive",
                last_name=f"{i+1:05d}",
                display_name=f"Executive {i+1}",
                email=f"executive{i+1}@example.com",
                phone=f"+1-555-{self.rng.randint(100,999)}-{self.rng.randint(1000,9999)}",
                avatar_url=None,
                designation=self.rng.choice(executive),
                status="active",
                department_id=dept_id,
                team_id=team_id,
                manager_id=None,  # Top level
                location_id=None,
                business_unit_id=None,
                employment_type="full_time",
                joining_date=utcnow().date() - timedelta(days=self.rng.randint(0, 1000)),
                timezone="UTC",
                language="en",
                bio=f"Bio for Executive {i+1}",
                emergency_contact={"name": "Emergency Contact", "phone": "+1-555-000-0000"},
                expertise_score=round(self.rng.uniform(80, 100), 1),
                profile_completion=100,
                ai_summary=f"AI summary for Executive {i+1}" if self.rng.random() < 0.2 else None,
            )
            self.db.add(emp)
            employee_ids.append(emp.id)
            self._created_ids["employees"].append(emp.id)
        
        # Create managers (5-10% of workforce)
        manager_count = max(1, self.profile.employee_count // 10)
        if is_large_org:
            manager_count = max(1, self.profile.employee_count // 8)
        
        for i in range(manager_count):
            dept_id = self.rng.choice(dept_ids) if dept_ids else None
            team_id = self.rng.choice(team_ids) if team_ids else None
            # Managers report to executives
            manager_id = self.rng.choice(employee_ids[:executive_count]) if executive_count > 0 else None
            
            emp = Employee(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_number=f"E{len(employee_ids)+1:05d}",
                first_name=f"Manager",
                last_name=f"{len(employee_ids)+1:05d}",
                display_name=f"Manager {len(employee_ids)+1}",
                email=f"manager{len(employee_ids)+1}@example.com",
                phone=f"+1-555-{self.rng.randint(100,999)}-{self.rng.randint(1000,9999)}",
                avatar_url=None,
                designation=self.rng.choice(management),
                status=self.rng.choice(statuses),
                department_id=dept_id,
                team_id=team_id,
                manager_id=manager_id,
                location_id=None,
                business_unit_id=None,
                employment_type=self.rng.choice(employment_types),
                joining_date=utcnow().date() - timedelta(days=self.rng.randint(0, 1000)),
                timezone="UTC",
                language="en",
                bio=f"Bio for Manager {len(employee_ids)+1}",
                emergency_contact={"name": "Emergency Contact", "phone": "+1-555-000-0000"},
                expertise_score=round(self.rng.uniform(60, 90), 1),
                profile_completion=self.rng.randint(70, 100),
                ai_summary=f"AI summary for Manager {len(employee_ids)+1}" if self.rng.random() < 0.2 else None,
            )
            self.db.add(emp)
            employee_ids.append(emp.id)
            self._created_ids["employees"].append(emp.id)
        
        # Create individual contributors (remaining)
        ic_count = self.profile.employee_count - executive_count - manager_count
        for i in range(ic_count):
            dept_id = self.rng.choice(dept_ids) if dept_ids else None
            team_id = self.rng.choice(team_ids) if team_ids else None
            # ICs report to managers
            manager_pool = employee_ids[executive_count:executive_count+manager_count]
            manager_id = self.rng.choice(manager_pool) if manager_pool else None
            
            emp = Employee(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_number=f"E{len(employee_ids)+1:05d}",
                first_name=f"Employee",
                last_name=f"{len(employee_ids)+1:05d}",
                display_name=f"Employee {len(employee_ids)+1}",
                email=f"employee{len(employee_ids)+1}@example.com",
                phone=f"+1-555-{self.rng.randint(100,999)}-{self.rng.randint(1000,9999)}",
                avatar_url=None,
                designation=self.rng.choice(individual_contributor),
                status=self.rng.choice(statuses),
                department_id=dept_id,
                team_id=team_id,
                manager_id=manager_id,
                location_id=None,
                business_unit_id=None,
                employment_type=self.rng.choice(employment_types),
                joining_date=utcnow().date() - timedelta(days=self.rng.randint(0, 1000)),
                timezone="UTC",
                language="en",
                bio=f"Bio for Employee {len(employee_ids)+1}",
                emergency_contact={"name": "Emergency Contact", "phone": "+1-555-000-0000"},
                expertise_score=round(self.rng.uniform(30, 80), 1),
                profile_completion=self.rng.randint(50, 100),
                ai_summary=f"AI summary for Employee {len(employee_ids)+1}" if self.rng.random() < 0.1 else None,
            )
            self.db.add(emp)
            employee_ids.append(emp.id)
            self._created_ids["employees"].append(emp.id)
        
        return len(employee_ids)
    
    def _generate_user_roles(self) -> int:
        # UserRole links users to roles, not employees directly
        # We need to get user IDs from employees
        employee_ids = self._created_ids["employees"]
        role_ids = self._created_ids["roles"]
        
        # Get user IDs from the database for these employees
        from sqlalchemy import select
        from app.models.employee import Employee
        result = self.db.execute(
            select(Employee.id, Employee.user_id).where(Employee.id.in_(employee_ids))
        )
        user_id_by_employee_id = {row.id: row.user_id for row in result}
        
        count = 0
        for emp_id in employee_ids:
            user_id = user_id_by_employee_id.get(emp_id)
            if not user_id:
                continue
            role_id = self.rng.choice(role_ids)
            ur = UserRole(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                user_id=user_id,
                role_id=role_id,
            )
            self.db.add(ur)
            count += 1
        
        return count
    
    def _generate_projects(self) -> int:
        team_ids = self._created_ids["teams"]
        employee_ids = self._created_ids["employees"]
        department_ids = self._created_ids.get("departments", [])
        
        priorities = ["low", "medium", "high", "critical"]
        health_statuses = ["green", "yellow", "red"]
        
        for i in range(self.config.project_count):
            team_id = self.rng.choice(team_ids) if team_ids else None
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.5 else None
            
            project = Project(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Project {i+1}",
                code=f"PRJ{i+1:04d}",
                description=f"Project {i+1} description",
                status=self.rng.choice(["planning", "active", "on_hold", "completed"]),
                priority=self.rng.choice(priorities),
                progress=self.rng.randint(0, 100),
                health=self.rng.choice(health_statuses),
                owner_id=owner_id,
                department_id=department_id,
                team_id=team_id,
                roadmap_id=None,
                start_date=utcnow().date() - timedelta(days=self.rng.randint(0, 365)),
                end_date=utcnow().date() + timedelta(days=self.rng.randint(0, 365)),
                budget=round(self.rng.uniform(10000, 500000), 2) if self.rng.random() < 0.5 else None,
                tags={"key": "value"} if self.rng.random() < 0.3 else None,
                ai_summary=f"AI summary for project {i+1}" if self.rng.random() < 0.2 else None,
            )
            self.db.add(project)
            self._created_ids["projects"].append(project.id)
        
        return self.config.project_count
    
    def _generate_tasks(self) -> int:
        project_ids = self._created_ids["projects"]
        employee_ids = self._created_ids["employees"]
        task_ids = self._created_ids.get("tasks", [])
        decision_ids = self._created_ids.get("decisions", [])
        goal_ids = self._created_ids.get("goals", [])
        
        # Model doesn't have a comment for status, but async uses: pending|in_progress|blocked|done|cancelled
        statuses = ["pending", "in_progress", "blocked", "done", "cancelled"]
        priorities = ["low", "medium", "high", "critical"]
        
        for i in range(self.config.task_count):
            project_id = self.rng.choice(project_ids) if project_ids else None
            assignee_id = self.rng.choice(employee_ids) if employee_ids else None
            reporter_id = self.rng.choice(employee_ids) if employee_ids else None
            epic_id = self.rng.choice(task_ids) if task_ids and self.rng.random() < 0.1 else None
            parent_task_id = self.rng.choice(task_ids) if task_ids and self.rng.random() < 0.15 else None
            decision_id = self.rng.choice(decision_ids) if decision_ids and self.rng.random() < 0.05 else None
            goal_id = self.rng.choice(goal_ids) if goal_ids and self.rng.random() < 0.1 else None
            
            status = self.rng.choice(statuses)
            completed_at = utcnow() - timedelta(days=self.rng.randint(0, 30)) if status == "done" and self.rng.random() < 0.7 else None
            
            task = Task(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Task {i+1}: {self.rng.choice(['Implement', 'Fix', 'Review', 'Design', 'Test', 'Deploy'])} {self.rng.choice(['API', 'UI', 'Database', 'Auth', 'Cache', 'Queue'])}",
                description=f"Detailed description for task {i+1}",
                status=status,
                priority=self.rng.choice(priorities),
                project_id=project_id,
                epic_id=epic_id,
                milestone_id=None,
                sprint_id=None,
                parent_task_id=parent_task_id,
                decision_id=decision_id,
                goal_id=goal_id,
                assignee_id=assignee_id,
                reporter_id=reporter_id,
                estimate_hours=self.rng.choice([1, 2, 3, 5, 8, 13, 21]),
                spent_hours=round(self.rng.uniform(0, 20), 1),
                start_date=utcnow().date() - timedelta(days=self.rng.randint(0, 30)) if self.rng.random() < 0.5 else None,
                due_date=utcnow().date() + timedelta(days=self.rng.randint(1, 60)) if self.rng.random() < 0.5 else None,
                completed_at=completed_at,
                progress=100 if status == "done" else self.rng.randint(0, 90),
                tags={"key": "value"} if self.rng.random() < 0.2 else None,
                ai_summary=f"AI summary for task {i+1}" if self.rng.random() < 0.1 else None,
                created_at=utcnow() - timedelta(days=self.rng.randint(0, 365)),
                updated_at=utcnow() - timedelta(days=self.rng.randint(0, 365)),
            )
            self.db.add(task)
            self._created_ids["tasks"].append(task.id)
        
        return self.config.task_count
    
    def _generate_goals(self) -> int:
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        department_ids = self._created_ids.get("departments", [])
        team_ids = self._created_ids.get("teams", [])
        goal_ids = self._created_ids.get("goals", [])
        
        # Async uses: active|completed|at_risk
        statuses = ["active", "completed", "at_risk"]
        scopes = ["org", "department", "team", "project"]
        priorities = ["low", "medium", "high", "critical"]
        
        for i in range(self.config.goal_count):
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            project_id = self.rng.choice(project_ids) if project_ids else None
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.3 else None
            team_id = self.rng.choice(team_ids) if team_ids and self.rng.random() < 0.3 else None
            parent_goal_id = self.rng.choice(goal_ids) if goal_ids and self.rng.random() < 0.1 else None
            
            goal = Goal(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Goal {i+1}: {self.rng.choice(['Increase', 'Improve', 'Reduce', 'Launch', 'Optimize'])} {self.rng.choice(['revenue', 'efficiency', 'churn', 'velocity', 'quality', 'coverage'])}",
                description=f"Strategic goal {i+1}",
                scope=self.rng.choice(scopes),
                owner_id=owner_id,
                department_id=department_id,
                team_id=team_id,
                project_id=project_id,
                status=self.rng.choice(statuses),
                progress=round(self.rng.uniform(0, 100), 1),
                priority=self.rng.choice(priorities),
                start_date=utcnow().date(),
                end_date=utcnow().date() + timedelta(days=self.rng.randint(30, 365)),
            )
            self.db.add(goal)
            self._created_ids["goals"].append(goal.id)
        
        return self.config.goal_count
    
    def _generate_meetings(self) -> int:
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids.get("projects", [])
        goal_ids = self._created_ids.get("goals", [])
        department_ids = self._created_ids.get("departments", [])
        team_ids = self._created_ids.get("teams", [])
        
        meeting_types = ["standup", "planning", "review", "retrospective", "one_on_one", "all_hands", "board", "client_call"]
        statuses = ["scheduled", "in_progress", "completed", "cancelled"]
        
        for i in range(self.config.meeting_count):
            organizer_id = self.rng.choice(employee_ids) if employee_ids else None
            project_id = self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None
            goal_id = self.rng.choice(goal_ids) if goal_ids and self.rng.random() < 0.2 else None
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.2 else None
            team_id = self.rng.choice(team_ids) if team_ids and self.rng.random() < 0.3 else None
            
            start_at = utcnow() + timedelta(days=self.rng.randint(-30, 30), hours=self.rng.randint(0, 23))
            end_at = start_at + timedelta(hours=self.rng.randint(1, 3))
            
            meeting = Meeting(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Meeting {i+1}: {self.rng.choice(['Sprint Planning', 'Retrospective', 'Code Review', '1:1', 'All Hands', 'Client Call', 'Board Meeting'])}",
                description=f"Meeting {i+1} description",
                meeting_type=self.rng.choice(meeting_types),
                status=self.rng.choice(statuses),
                organizer_id=organizer_id,
                project_id=project_id,
                goal_id=goal_id,
                department_id=department_id,
                team_id=team_id,
                calendar_event_id=None,
                room_id=None,
                meeting_code=f"MTG{i+1:04d}",
                timezone="UTC",
                duration_minutes=self.rng.choice([15, 30, 45, 60, 90, 120]),
                start_at=start_at,
                end_at=end_at,
                location=self.rng.choice(["Conference Room A", "Conference Room B", "Zoom", "Teams", "Google Meet"]) if self.rng.random() < 0.7 else None,
                meeting_link=f"https://meet.example.com/{uuid.uuid4().hex[:8]}" if self.rng.random() < 0.5 else None,
                transcript_summary=f"Transcript summary for meeting {i+1}" if self.rng.random() < 0.2 else None,
                ai_summary=f"AI summary for meeting {i+1}" if self.rng.random() < 0.2 else None,
            )
            self.db.add(meeting)
            self._created_ids["meetings"].append(meeting.id)
        
        return self.config.meeting_count
    
    def _generate_decisions(self) -> int:
        project_ids = self._created_ids["projects"]
        employee_ids = self._created_ids["employees"]
        goal_ids = self._created_ids.get("goals", [])
        meeting_ids = self._created_ids.get("meetings", [])
        department_ids = self._created_ids.get("departments", [])
        
        statuses = ["proposed", "approved", "rejected", "implemented"]
        
        for i in range(self.config.decision_count):
            project_id = self.rng.choice(project_ids) if project_ids else None
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            goal_id = self.rng.choice(goal_ids) if goal_ids and self.rng.random() < 0.2 else None
            meeting_id = self.rng.choice(meeting_ids) if meeting_ids and self.rng.random() < 0.2 else None
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.2 else None
            
            # Use counter + UUID for guaranteed unique slug
            slug = f"dec-{i+1:08d}-{uuid.uuid4().hex[:8]}"
            
            decision = Decision(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Decision {i+1}: {self.rng.choice(['Adopt', 'Reject', 'Defer', 'Modify', 'Approve'])} {self.rng.choice(['New Technology', 'Process Change', 'Budget Allocation', 'Hiring Plan', 'Strategy Shift'])}",
                slug=slug,
                description=f"Decision {i+1} description",
                content=f"Full content for decision {i+1}",
                context=f"Context for decision {i+1}",
                summary=f"Summary for decision {i+1}",
                ai_summary=f"AI summary for decision {i+1}" if self.rng.random() < 0.2 else None,
                keywords=f"keyword1, keyword2, keyword3" if self.rng.random() < 0.3 else None,
                status=self.rng.choice(statuses),
                decision_maker_id=owner_id,
                decision_date=utcnow().date() - timedelta(days=self.rng.randint(0, 365)),
                impact=f"Impact analysis for decision {i+1}",
                business_impact=f"Business impact for decision {i+1}",
                follow_up_actions=[f"Action {j+1}" for j in range(self.rng.randint(1, 3))] if self.rng.random() < 0.5 else [],
                future_review_date=utcnow().date() + timedelta(days=self.rng.randint(30, 365)) if self.rng.random() < 0.3 else None,
                lessons_learned=f"Lessons learned from decision {i+1}" if self.rng.random() < 0.3 else None,
                project_id=project_id,
                goal_id=goal_id,
                meeting_id=meeting_id,
                department_id=department_id,
                version=1,
                view_count=self.rng.randint(0, 100),
                decided_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(decision)
            self._created_ids["decisions"].append(decision.id)
        
        return self.config.decision_count
    
    def _generate_documents(self) -> int:
        project_ids = self._created_ids["projects"]
        employee_ids = self._created_ids["employees"]
        department_ids = self._created_ids.get("departments", [])
        team_ids = self._created_ids.get("teams", [])
        
        categories = ["spec", "design", "report", "meeting_notes", "policy", "guide", "reference", "template"]
        statuses = ["draft", "review", "approved", "archived"]
        visibilities = ["private", "team", "department", "organization", "public"]
        
        for i in range(self.config.document_count):
            project_id = self.rng.choice(project_ids) if project_ids else None
            author_id = self.rng.choice(employee_ids) if employee_ids else None
            owner_id = self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.5 else author_id
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.3 else None
            team_id = self.rng.choice(team_ids) if team_ids and self.rng.random() < 0.3 else None
            
            doc = Document(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Document {i+1}: {self.rng.choice(['API Spec', 'Design Doc', 'Project Report', 'Meeting Notes', 'Architecture Decision', 'User Guide'])}",
                slug=f"doc-{i+1:08d}-{uuid.uuid4().hex[:8]}",
                description=f"Document {i+1} description",
                content=f"Content of document {i+1}",
                summary=f"Summary of document {i+1}",
                ai_summary=f"AI summary for document {i+1}" if self.rng.random() < 0.2 else None,
                keywords=f"keyword1, keyword2, keyword3" if self.rng.random() < 0.3 else None,
                category=self.rng.choice(categories),
                author_id=author_id,
                owner_id=owner_id,
                project_id=project_id,
                department_id=department_id,
                team_id=team_id,
                status=self.rng.choice(statuses),
                visibility=self.rng.choice(visibilities),
                version=self.rng.randint(1, 5),
                view_count=self.rng.randint(0, 1000),
                published_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(doc)
            self._created_ids["documents"].append(doc.id)
        
        return self.config.document_count
    
    def _generate_wiki_pages(self) -> int:
        project_ids = self._created_ids.get("projects", [])
        department_ids = self._created_ids.get("departments", [])
        team_ids = self._created_ids.get("teams", [])
        employee_ids = self._created_ids.get("employees", [])
        wiki_page_ids = self._created_ids.get("wiki_pages", [])
        
        spaces = ["engineering", "product", "design", "marketing", "sales", "hr", "finance", "general"]
        statuses = ["draft", "published", "archived"]
        categories = ["guide", "reference", "tutorial", "faq", "policy", "process"]
        
        for i in range(self.config.wiki_page_count):
            project_id = self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.2 else None
            team_id = self.rng.choice(team_ids) if team_ids and self.rng.random() < 0.2 else None
            author_id = self.rng.choice(employee_ids) if employee_ids else None
            editor_id = self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.3 else author_id
            parent_id = self.rng.choice(wiki_page_ids) if wiki_page_ids and self.rng.random() < 0.1 else None
            
            page = WikiPage(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                space=self.rng.choice(spaces),
                title=f"Wiki Page {i+1}: {self.rng.choice(['Getting Started', 'API Reference', 'Architecture', 'Best Practices', 'Troubleshooting', 'Onboarding'])}",
                slug=f"wiki-{i+1:08d}-{uuid.uuid4().hex[:8]}",
                description=f"Description for wiki page {i+1}",
                content=f"Content of wiki page {i+1}",
                summary=f"Summary of wiki page {i+1}",
                ai_summary=f"AI summary for wiki page {i+1}" if self.rng.random() < 0.2 else None,
                keywords=f"keyword1, keyword2, keyword3" if self.rng.random() < 0.3 else None,
                category=self.rng.choice(categories),
                author_id=author_id,
                editor_id=editor_id,
                parent_id=parent_id,
                project_id=project_id,
                department_id=department_id,
                team_id=team_id,
                status=self.rng.choice(statuses),
                version=self.rng.randint(1, 5),
                view_count=self.rng.randint(0, 500),
                published_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(page)
            self._created_ids["wiki_pages"].append(page.id)
        
        return self.config.wiki_page_count
    
    def _generate_policies(self) -> int:
        employee_ids = self._created_ids.get("employees", [])
        
        categories = ["hr", "security", "finance", "operations", "compliance", "data", "it"]
        statuses = ["draft", "active", "archived"]
        
        for i in range(self.config.policy_count):
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            approver_id = self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.5 else None
            
            policy = Policy(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Policy {i+1}: {self.rng.choice(['Data Protection', 'Access Control', 'Expense Policy', 'Security Policy', 'HR Policy', 'Compliance Policy'])}",
                slug=f"policy-{i+1:08d}-{uuid.uuid4().hex[:8]}",
                description=f"Policy {i+1} description",
                content=f"Policy {i+1} content",
                summary=f"Summary of policy {i+1}",
                ai_summary=f"AI summary for policy {i+1}" if self.rng.random() < 0.2 else None,
                keywords=f"keyword1, keyword2, keyword3" if self.rng.random() < 0.3 else None,
                category=self.rng.choice(categories),
                owner_id=owner_id,
                approver_id=approver_id,
                effective_date=utcnow().date() if self.rng.random() < 0.5 else None,
                review_date=utcnow().date() + timedelta(days=self.rng.randint(90, 365)) if self.rng.random() < 0.5 else None,
                approval_note=f"Approved by {approver_id[:8]}" if approver_id else None,
                status=self.rng.choice(statuses),
                version=self.rng.randint(1, 3),
                view_count=self.rng.randint(0, 200),
                published_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(policy)
            self._created_ids["policies"].append(policy.id)
        
        return self.config.policy_count
    
    def _generate_sops(self) -> int:
        employee_ids = self._created_ids.get("employees", [])
        department_ids = self._created_ids.get("departments", [])
        team_ids = self._created_ids.get("teams", [])
        
        categories = ["engineering", "hr", "finance", "security", "operations", "it", "compliance"]
        statuses = ["draft", "active", "archived"]
        
        for i in range(self.config.sop_count):
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            department_id = self.rng.choice(department_ids) if department_ids and self.rng.random() < 0.3 else None
            team_id = self.rng.choice(team_ids) if team_ids and self.rng.random() < 0.3 else None
            
            sop = SOP(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"SOP {i+1}: {self.rng.choice(['Deployment Process', 'Code Review', 'Incident Response', 'Onboarding', 'Offboarding', 'Backup Procedure', 'Security Audit'])}",
                slug=f"sop-{i+1:08d}-{uuid.uuid4().hex[:8]}",
                description=f"SOP {i+1} description",
                content=f"SOP {i+1} content",
                summary=f"Summary of SOP {i+1}",
                ai_summary=f"AI summary for SOP {i+1}" if self.rng.random() < 0.2 else None,
                keywords=f"keyword1, keyword2, keyword3" if self.rng.random() < 0.3 else None,
                category=self.rng.choice(categories),
                owner_id=owner_id,
                department_id=department_id,
                team_id=team_id,
                status=self.rng.choice(statuses),
                version=self.rng.randint(1, 3),
                view_count=self.rng.randint(0, 200),
                published_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(sop)
            self._created_ids["sops"].append(sop.id)
        
        return self.config.sop_count
    
    def _generate_templates(self) -> int:
        employee_ids = self._created_ids.get("employees", [])
        
        kinds = ["document", "email", "meeting", "report", "presentation", "form"]
        categories = ["general", "engineering", "hr", "finance", "marketing", "sales"]
        statuses = ["draft", "active", "archived"]
        
        for i in range(self.config.template_count):
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            
            template = Template(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Template {i+1}: {self.rng.choice(['Project Plan', 'Meeting Agenda', 'Email Template', 'Report Template', 'Document Template', 'Form Template'])}",
                slug=f"tpl-{i+1:08d}-{uuid.uuid4().hex[:8]}",
                description=f"Template {i+1} description",
                content=f"Template {i+1} content",
                summary=f"Summary of template {i+1}",
                ai_summary=f"AI summary for template {i+1}" if self.rng.random() < 0.2 else None,
                keywords=f"keyword1, keyword2, keyword3" if self.rng.random() < 0.3 else None,
                kind=self.rng.choice(kinds),
                category=self.rng.choice(categories),
                owner_id=owner_id,
                status=self.rng.choice(statuses),
                version=self.rng.randint(1, 3),
                usage_count=self.rng.randint(0, 100),
                view_count=self.rng.randint(0, 200),
                published_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.5 else None,
            )
            self.db.add(template)
            self._created_ids["templates"].append(template.id)
        
        return self.config.template_count
    
    def _generate_conversations(self) -> int:
        employee_ids = self._created_ids["employees"]
        
        channel_kinds = ["direct", "channel", "group", "announcement"]
        types = ["dm", "channel", "announcement"]
        
        for i in range(self.config.conversation_count):
            created_by = self.rng.choice(employee_ids) if employee_ids else None
            
            conv = Conversation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                title=f"Conversation {i+1}: {self.rng.choice(['Project Discussion', 'Team Chat', 'Announcement', 'Direct Message', 'Support Thread'])}",
                channel_kind=self.rng.choice(channel_kinds),
                type=self.rng.choice(types),
                channel_key=f"channel-{uuid.uuid4().hex[:8]}" if self.rng.random() < 0.5 else None,
                community_id=None,
                created_by=created_by,
                is_archived=self.rng.random() < 0.1,
                last_message_at=utcnow() - timedelta(hours=self.rng.randint(0, 168)) if self.rng.random() < 0.8 else None,
                message_count=self.rng.randint(0, 100),
            )
            self.db.add(conv)
            self._created_ids["conversations"].append(conv.id)
            
            # Add members
            if employee_ids:
                member_count = min(self.rng.randint(2, 5), len(employee_ids))
                members = self.rng.sample(employee_ids, member_count)
                for emp_id in members:
                    member = ConversationMember(
                        id=uuid.uuid4().hex[:32],
                        organization_id=self.org_id,
                        conversation_id=conv.id,
                        employee_id=emp_id,
                        role=self.rng.choice(["owner", "admin", "member"]),
                        last_read_at=utcnow() - timedelta(hours=self.rng.randint(0, 24)) if self.rng.random() < 0.8 else None,
                        notifications_enabled=self.rng.random() < 0.9,
                        joined_at=utcnow() - timedelta(days=self.rng.randint(0, 365)),
                    )
                    self.db.add(member)
        
        return self.config.conversation_count
    
    def _generate_messages(self) -> int:
        conversation_ids = self._created_ids["conversations"]
        employee_ids = self._created_ids["employees"]
        message_ids = self._created_ids.get("messages", [])
        
        for i in range(self.config.message_count):
            conv_id = self.rng.choice(conversation_ids) if conversation_ids else None
            sender_id = self.rng.choice(employee_ids) if employee_ids else None
            
            if not conv_id or not sender_id:
                continue
            
            reply_to = self.rng.choice(message_ids) if message_ids and self.rng.random() < 0.1 else None
            
            msg = Message(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                conversation_id=conv_id,
                sender_id=sender_id,
                content=f"Message {i+1} content: {self.rng.choice(['Hello team', 'Please review', 'Approved', 'Question about', 'Update on', 'Reminder:', 'Thanks!'])}",
                reply_to=reply_to,
                edited=self.rng.random() < 0.05,
                edited_at=utcnow() - timedelta(minutes=self.rng.randint(1, 60)) if self.rng.random() < 0.05 else None,
                deleted=self.rng.random() < 0.02,
                deleted_at=utcnow() - timedelta(minutes=self.rng.randint(1, 60)) if self.rng.random() < 0.02 else None,
                attachments=[{"type": "file", "name": f"file_{i}.pdf"}] if self.rng.random() < 0.1 else [],
                mentions=[emp_id[:8] for emp_id in self.rng.sample(employee_ids, min(3, len(employee_ids)))] if self.rng.random() < 0.1 and employee_ids else [],
                reaction_count=self.rng.randint(0, 10),
            )
            self.db.add(msg)
            self._created_ids["messages"].append(msg.id)
        
        return self.config.message_count
    
    def _generate_budgets(self) -> int:
        department_ids = self._created_ids["departments"]
        team_ids = self._created_ids.get("teams", [])
        project_ids = self._created_ids.get("projects", [])
        employee_ids = self._created_ids["employees"]
        
        # Model comment: annual|quarterly|department|project|team|initiative|training|marketing|rnd|travel|it|other
        budget_types = ["annual", "quarterly", "department", "project", "team", "initiative", "marketing", "rnd", "travel", "it", "other"]
        # Model comment: draft|active|frozen|closed
        statuses = ["draft", "active", "frozen", "closed"]
        risk_levels = ["low", "medium", "high", "critical"]
        
        for i in range(self.config.budget_count):
            dept_id = self.rng.choice(department_ids) if department_ids else None
            team_id = self.rng.choice(team_ids) if team_ids and self.rng.random() < 0.3 else None
            project_id = self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None
            owner_id = self.rng.choice(employee_ids) if employee_ids else None
            
            allocated = round(self.rng.uniform(10000, 5000000), 2)
            used = round(self.rng.uniform(0, allocated * 0.8), 2)
            remaining = allocated - used
            
            budget = Budget(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Budget {i+1}: {self.rng.choice(['Annual Ops', 'Project Fund', 'Marketing', 'R&D', 'Travel', 'IT', 'Training', 'Quarterly Planning'])}",
                budget_type=self.rng.choice(budget_types),
                department_id=dept_id,
                project_id=project_id,
                team_id=team_id,
                fiscal_year=utcnow().year,
                period_start=utcnow().date().replace(month=1, day=1),
                period_end=utcnow().date().replace(month=12, day=31),
                allocated_amount=allocated,
                used_amount=used,
                remaining_amount=remaining,
                currency="USD",
                status=self.rng.choice(statuses),
                owner_id=owner_id,
                forecast_amount=round(self.rng.uniform(0, 5000000), 2),
                risk_level=self.rng.choice(risk_levels),
                description=f"Budget {i+1} description",
                attributes={} if self.rng.random() < 0.2 else None,
            )
            self.db.add(budget)
            self._created_ids["budgets"].append(budget.id)
        
        return self.config.budget_count
    
    def _generate_vendors(self) -> int:
        # Model comment: supplier|vendor|consultant|contractor|partner
        kinds = ["supplier", "vendor", "consultant", "contractor", "partner"]
        # Model default: active
        statuses = ["active", "inactive", "blacklisted"]
        
        for i in range(self.config.vendor_count):
            vendor = Vendor(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Vendor {i+1} {self.rng.choice(['Inc', 'LLC', 'Corp', 'Ltd'])}",
                kind=self.rng.choice(kinds),
                contact_name=self.rng.choice(["John Smith", "Jane Doe", "Bob Wilson", "Alice Brown", "Charlie Davis"]),
                email=f"vendor{i+1}@example.com",
                phone=f"+1-555-{self.rng.randint(100,999)}-{self.rng.randint(1000,9999)}",
                website=f"https://vendor{i+1}.example.com",
                country=self.rng.choice(["US", "UK", "DE", "FR", "CA", "AU"]),
                tax_id=f"TAX{self.rng.randint(10000000, 99999999)}",
                payment_terms=self.rng.choice(["net30", "net60", "net90", "due_on_receipt"]),
                rating=self.rng.randint(1, 5),
                performance_score=self.rng.randint(0, 100),
                status=self.rng.choice(statuses),
                description=f"Vendor {i+1} description",
                attributes={} if self.rng.random() < 0.2 else None,
            )
            self.db.add(vendor)
            self._created_ids["vendors"].append(vendor.id)
        
        return self.config.vendor_count
    
    def _generate_invoices(self) -> int:
        vendor_ids = self._created_ids["vendors"]
        customer_ids = self._created_ids.get("customers", [])
        project_ids = self._created_ids.get("projects", [])
        employee_ids = self._created_ids["employees"]
        
        # Model comment: draft|pending|approved|paid|overdue|void|cancelled
        statuses = ["draft", "pending", "approved", "paid", "overdue", "void", "cancelled"]
        
        for i in range(self.config.invoice_count):
            vendor_id = self.rng.choice(vendor_ids) if vendor_ids else None
            customer_id = self.rng.choice(customer_ids) if customer_ids and self.rng.random() < 0.5 else None
            project_id = self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None
            
            invoice = Invoice(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                vendor_id=vendor_id,
                customer_id=customer_id,
                project_id=project_id,
                invoice_number=f"INV-{20240000 + i}",
                reference_number=f"REF-{i+1:06d}" if self.rng.random() < 0.3 else None,
                title=f"Invoice {i+1}",
                amount=round(self.rng.uniform(100, 50000), 2),
                tax_amount=round(self.rng.uniform(0, 5000), 2),
                currency="USD",
                direction=self.rng.choice(["payable", "receivable"]),
                status=self.rng.choice(statuses),
                issued_at=utcnow().date() - timedelta(days=self.rng.randint(0, 365)),
                due_at=utcnow().date() + timedelta(days=self.rng.randint(1, 90)),
                paid_at=utcnow() - timedelta(days=self.rng.randint(0, 30)) if self.rng.random() < 0.3 else None,
                payment_reference=f"PAY-{i+1:06d}" if self.rng.random() < 0.3 else None,
                external_system=self.rng.choice(["quickbooks", "xero", "sap", "netsuite"]) if self.rng.random() < 0.1 else None,
                external_id=f"EXT-{i+1:06d}" if self.rng.random() < 0.1 else None,
                attributes={} if self.rng.random() < 0.2 else None,
            )
            self.db.add(invoice)
            self._created_ids["invoices"].append(invoice.id)
        
        return self.config.invoice_count
    
    def _generate_purchase_orders(self) -> int:
        vendor_ids = self._created_ids["vendors"]
        purchase_request_ids = self._created_ids.get("purchase_requests", [])
        project_ids = self._created_ids.get("projects", [])
        
        # Model comment: draft|issued|accepted|partially_delivered|delivered|closed|cancelled
        statuses = ["draft", "issued", "accepted", "partially_delivered", "delivered", "closed", "cancelled"]
        
        for i in range(self.config.purchase_order_count):
            vendor_id = self.rng.choice(vendor_ids) if vendor_ids else None
            purchase_request_id = self.rng.choice(purchase_request_ids) if purchase_request_ids and self.rng.random() < 0.5 else None
            project_id = self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.3 else None
            
            po = PurchaseOrder(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                purchase_request_id=purchase_request_id,
                vendor_id=vendor_id,
                project_id=project_id,
                po_number=f"PO-{20240000 + i}",
                title=f"PO {i+1}: {self.rng.choice(['Software License', 'Hardware', 'Consulting', 'Cloud Credits', 'Support'])}",
                total_amount=round(self.rng.uniform(1000, 500000), 2),
                currency="USD",
                status=self.rng.choice(statuses),
                issued_at=utcnow() - timedelta(days=self.rng.randint(0, 365)) if self.rng.random() < 0.7 else None,
                expected_delivery_at=utcnow().date() + timedelta(days=self.rng.randint(1, 60)) if self.rng.random() < 0.7 else None,
                delivered_at=utcnow() - timedelta(days=self.rng.randint(0, 30)) if self.rng.random() < 0.3 else None,
                external_reference=f"EXT-{i+1:06d}" if self.rng.random() < 0.2 else None,
                attributes={} if self.rng.random() < 0.2 else None,
            )
            self.db.add(po)
            self._created_ids["purchase_orders"].append(po.id)
        
        return self.config.purchase_order_count
    
    def _generate_purchase_requests(self) -> int:
        employee_ids = self._created_ids["employees"]
        vendor_ids = self._created_ids["vendors"]
        project_ids = self._created_ids.get("projects", [])
        budget_ids = self._created_ids.get("budgets", [])
        
        # Model comment: draft|submitted|manager_approved|finance_approved|approved|rejected|cancelled|ordered
        statuses = ["draft", "submitted", "manager_approved", "finance_approved", "approved", "rejected", "cancelled", "ordered"]
        categories = ["laptop", "monitor", "software", "furniture", "services", "cloud", "training", "equipment", "marketing", "other"]
        
        for i in range(self.config.purchase_request_count):
            requester_id = self.rng.choice(employee_ids) if employee_ids else None
            vendor_id = self.rng.choice(vendor_ids) if vendor_ids else None
            project_id = self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.5 else None
            budget_id = self.rng.choice(budget_ids) if budget_ids and self.rng.random() < 0.3 else None
            approver_id = self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.5 else None
            status = self.rng.choice(statuses)
            
            pr = PurchaseRequest(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_id=requester_id,
                title=f"Purchase Request {i+1}: {self.rng.choice(['New Laptop', 'Software License', 'Cloud Credits', 'Training', 'Conference', 'Equipment', 'Monitor', 'Furniture'])}",
                description=f"Purchase request {i+1} description",
                category=self.rng.choice(categories),
                quantity=self.rng.randint(1, 10),
                estimated_cost=round(self.rng.uniform(100, 10000), 2),
                currency="USD",
                vendor_name=f"Vendor {vendor_id[:8]}" if vendor_id else None,
                vendor_id=vendor_id,
                project_id=project_id,
                budget_id=budget_id,
                status=status,
                approver_id=approver_id if status in ["manager_approved", "finance_approved", "approved", "rejected"] else None,
                approved_at=utcnow() - timedelta(days=self.rng.randint(0, 30)) if status in ["manager_approved", "finance_approved", "approved"] else None,
                rejection_reason=f"Rejected: {self.rng.choice(['Budget exceeded', 'Not approved by manager', 'Duplicate request', 'Policy violation'])}" if status == "rejected" else None,
                policy_flags={"requires_manager_approval": True} if self.rng.random() < 0.3 else {},
                attributes={} if self.rng.random() < 0.2 else None,
            )
            self.db.add(pr)
            self._created_ids["purchase_requests"].append(pr.id)
        
        return self.config.purchase_request_count
    
    def _generate_expenses(self) -> int:
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        budget_ids = self._created_ids.get("budgets", [])
        
        expense_types = ["travel", "food", "office", "software", "hardware", "training", "marketing", "client", "cloud", "miscellaneous"]
        statuses = ["draft", "submitted", "pending", "approved", "rejected", "reimbursed"]
        
        for i in range(self.config.expense_count):
            employee_id = self.rng.choice(employee_ids) if employee_ids else None
            project_id = self.rng.choice(project_ids) if project_ids else None
            budget_id = self.rng.choice(budget_ids) if budget_ids and self.rng.random() < 0.3 else None
            
            expense = Expense(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                employee_id=employee_id,
                expense_type=self.rng.choice(expense_types),
                amount=round(self.rng.uniform(10, 5000), 2),
                currency="USD",
                incurred_at=utcnow().date() - timedelta(days=self.rng.randint(0, 365)),
                merchant=self.rng.choice(["Delta Airlines", "Marriott", "Amazon", "Microsoft", "Local Restaurant", "Uber", "Office Depot"]) if self.rng.random() < 0.7 else None,
                description=f"Expense {i+1}: {self.rng.choice(['Flight', 'Hotel', 'Meal', 'Software License', 'Book', 'Course', 'Office Supplies', 'Cloud Credits', 'Client Dinner'])}",
                project_id=project_id,
                budget_id=budget_id,
                status=self.rng.choice(statuses),
            )
            self.db.add(expense)
            self._created_ids["expenses"].append(expense.id)
        
        return self.config.expense_count
    
    def _generate_customers(self) -> int:
        employee_ids = self._created_ids["employees"]
        industries = ["Technology", "Finance", "Healthcare", "Retail", "Manufacturing", "Education", "Government", "Media"]
        statuses = ["active"] * 70 + ["prospect"] * 15 + ["churned"] * 10 + ["onboarding"] * 5
        segments = ["enterprise", "mid_market", "smb", "startup", "government", "nonprofit"]
        tiers = ["basic", "silver", "gold", "platinum", "enterprise"]
        sources = ["website", "referral", "marketing", "events", "cold_outreach", "partner", "advertisement"]
        count = max(1, self.config.employee_count // 10)
        for i in range(count):
            customer = Customer(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                company_name=f"Customer {i+1} {self.rng.choice(['Inc', 'LLC', 'Corp', 'Ltd', 'GmbH'])}",
                industry=self.rng.choice(industries),
                status=self.rng.choice(statuses),
                segment=self.rng.choice(segments),
                tier=self.rng.choice(tiers),
                country=self.rng.choice(["US", "UK", "DE", "FR", "CA", "AU", "JP", "SG"]),
                website=f"https://customer{i+1}.example.com",
                description=f"Customer {i+1} description",
                source=self.rng.choice(sources),
                owner_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.7 else None,
                employee_count=self.rng.randint(10, 10000),
                health_score=self.rng.randint(0, 100),
                health_status=self.rng.choice(["healthy", "at_risk", "critical", "unknown"]),
                annual_value=round(self.rng.uniform(10000, 5000000), 2),
            )
            self.db.add(customer)
            self._created_ids["customers"].append(customer.id)
        
        return count
    
    def _generate_integrations(self) -> int:
        # Need connector IDs from the database
        # Flush first to avoid autoflush issues with pending objects
        self.db.flush()
        from sqlalchemy import select
        from app.models.canonical_integration import Connector
        result = self.db.execute(select(Connector.id))
        connector_ids = [row.id for row in result]
        if not connector_ids:
            return 0
        
        for i in range(self.config.integration_count):
            integration = ConnectorInstance(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                name=f"Integration {i+1}",
                connector_id=self.rng.choice(connector_ids),
                state=self.rng.choice(["connected", "disconnected", "error"]),
                config={},
            )
            self.db.add(integration)
            self._created_ids["integrations"].append(integration.id)
        
        return self.config.integration_count
    
    def _generate_security_events(self) -> int:
        """Generate security events using COPY for maximum performance."""
        import io
        import csv
        
        # SecurityEvent.actor_id references users.id, not employees.id
        # Get user IDs from employees
        employee_ids = self._created_ids["employees"]
        from sqlalchemy import select
        from app.models.employee import Employee
        result = self.db.execute(
            select(Employee.id, Employee.user_id).where(Employee.id.in_(employee_ids))
        )
        user_id_by_employee_id = {row.id: row.user_id for row in result}
        
        event_types = [
            "failed_login", "failed_login_brute_force", "successful_login_new_device",
            "password_reset", "mfa_enabled", "mfa_disabled", "role_changed",
            "permission_escalation", "data_export", "unusual_access_pattern",
            "api_key_created", "api_key_revoked", "webhook_created", "integration_modified"
        ]
        severities = ["low"] * 50 + ["medium"] * 30 + ["high"] * 15 + ["critical"] * 5
        statuses = ["open"] * 30 + ["investigating"] * 20 + ["resolved"] * 40 + ["false_positive"] * 10
        
        # Column order must match table definition
        columns = [
            "id", "organization_id", "event_type", "severity", "title",
            "actor_id", "source_ip", "details", "status",
            "resolved_by", "resolved_at", "created_at", "updated_at"
        ]
        
        # Use COPY for bulk insert
        raw_conn = self.db.connection().connection
        cursor = None
        event_ids = []
        
        # Conservative batch size to avoid memory/WAL pressure
        if self.config.security_event_count > 100000:
            batch_size = 1000
        elif self.config.security_event_count > 10000:
            batch_size = 2500
        else:
            batch_size = 5000
        
        try:
            cursor = raw_conn.cursor()
            
            for batch_start in range(0, self.config.security_event_count, batch_size):
                batch_end = min(batch_start + batch_size, self.config.security_event_count)
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                now = utcnow()
                
                for i in range(batch_start, batch_end):
                    employee_id = self.rng.choice(employee_ids) if employee_ids else None
                    user_id = user_id_by_employee_id.get(employee_id) if employee_id else None
                    days_ago = self.rng.randint(0, 365 * self.config.years_of_history)
                    
                    event_id = uuid.uuid4().hex[:32]
                    
                    row = [
                        event_id,
                        self.org_id,
                        self.rng.choice(event_types),
                        self.rng.choice(severities),
                        f"Security Event {i+1}: {self.rng.choice(event_types).replace('_', ' ').title()}",
                        user_id,
                        f"{self.rng.randint(1,255)}.{self.rng.randint(1,255)}.{self.rng.randint(1,255)}.{self.rng.randint(1,255)}",
                        json.dumps({"attempts": self.rng.randint(1, 100), "duration_seconds": self.rng.randint(60, 3600)}),
                        self.rng.choice(statuses),
                        None,  # resolved_by
                        None,  # resolved_at
                        now - timedelta(days=days_ago, hours=self.rng.randint(0, 23)),
                        now,
                    ]
                    writer.writerow(row)
                    event_ids.append(event_id)
                
                output.seek(0)
                cursor.copy_expert(
                    f"COPY security_events ({', '.join(columns)}) FROM STDIN WITH (FORMAT CSV)",
                    output
                )
                raw_conn.commit()
            
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
        
        self._created_ids["security_events"].extend(event_ids)
        
        return self.config.security_event_count
    
    def _generate_operations(self) -> int:
        op_types = ["api_call", "webhook", "sync", "batch_job", "report", "export", "import", "migration"]
        states = ["completed"] * 70 + ["failed"] * 10 + ["unknown"] * 5 + ["retrying"] * 10 + ["queued"] * 5
        
        employee_ids = self._created_ids["employees"]
        project_ids = self._created_ids["projects"]
        
        count = max(1, self.config.employee_count * 5)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:op:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            op = CanonicalOperation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                operation_type=self.rng.choice(op_types),
                title=f"Operation {i+1}: {self.rng.choice(op_types).replace('_', ' ').title()}",
                description=f"Operation {i+1} description",
                scope_type="project" if project_ids and self.rng.random() < 0.5 else "company",
                scope_id=self.rng.choice(project_ids) if project_ids and self.rng.random() < 0.5 else None,
                actor_id=self.rng.choice(employee_ids) if employee_ids else None,
                actor_type="human",
                is_external=self.rng.random() < 0.2,
                external_system=self.rng.choice(["github", "slack", "jira", "salesforce"]) if self.rng.random() < 0.2 else None,
                state=self.rng.choice(states),
                current_attempt=self.rng.randint(1, 3),
                max_attempts=3,
                retry_policy="exponential_backoff",
                fingerprint=fingerprint,
            )
            self.db.add(op)
            self._created_ids["operations"].append(op.id)
        
        self.db.flush()
        
        # Generate attempts for operations
        for op_id in self._created_ids["operations"]:
            attempt_count = self.rng.randint(1, 3)
            for a in range(attempt_count):
                fingerprint = hashlib.sha256(
                    f"{self.org_id}:attempt:{op_id}:{a}:{self.rng.random()}".encode()
                ).hexdigest()[:160]
                attempt = OperationAttempt(
                    id=uuid.uuid4().hex[:32],
                    operation_id=op_id,
                    organization_id=self.org_id,
                    attempt_number=a + 1,
                    state=self.rng.choice(["completed", "completed", "failed", "executing"]),
                    worker_id="worker-1",
                    worker_instance="instance-1",
                    started_at=utcnow() - timedelta(days=self.rng.randint(0, 30)),
                    completed_at=utcnow() - timedelta(days=self.rng.randint(0, 30), hours=-1),
                    outcome=self.rng.choice(["success", "success", "failure", "timeout"]),
                    duration_ms=self.rng.randint(100, 300000),
                    fingerprint=fingerprint,
                )
                self.db.add(attempt)
        
        return count
    
    def _generate_observations(self) -> int:
        """Generate canonical observations using ORM bulk insert for consistency."""
        
        obs_types = [
            "request", "worker_execution", "operation_lifecycle", "integration_sync",
            "external_operation", "security_event", "recovery_action", "reconciliation",
            "health_check", "freshness_check", "slo_evaluation", "attention_signal",
            "degradation", "correlation"
        ]
        sources = ["api", "worker", "integration", "database", "cache", "queue", "scheduler", "webhook"]
        severities = ["debug"] * 30 + ["info"] * 40 + ["notice"] * 15 + ["warning"] * 10 + ["critical"] * 5
        # Distribute epistemic statuses per the canonical model's check constraint
        epistemic_statuses = (
            ["observed"] * 30 + ["measured"] * 20 + ["evidence_backed"] * 20 +
            ["inferred"] * 15 + ["predicted"] * 10 + ["unknown"] * 5
        )
        
        employee_ids = self._created_ids["employees"]
        operation_ids = self._created_ids["operations"]
        integration_ids = self._created_ids["integrations"]
        
        observation_ids = []
        batch_size = 1000
        now = utcnow()
        
        for batch_start in range(0, self.config.observation_count, batch_size):
            batch_end = min(batch_start + batch_size, self.config.observation_count)
            
            batch_observations = []
            
            for i in range(batch_start, batch_end):
                days_ago = self.rng.randint(0, 365 * self.config.years_of_history)
                
                obs_id = uuid.uuid4().hex[:32]
                fingerprint = hashlib.sha256(
                    f"{self.org_id}:{i}:{self.rng.random()}".encode()
                ).hexdigest()[:160]
                
                # Generate source event ID for provenance
                source_event_id = f"evt-{uuid.uuid4().hex[:24]}"
                
                # Select epistemic status
                epistemic_status = self.rng.choice(epistemic_statuses)
                
                # Build provenance JSON with coherent synthetic lineage
                obs_type = self.rng.choice(obs_types)
                source = self.rng.choice(sources)
                provenance = {
                    "source_type": source,
                    "source_component": f"{source}-{self.rng.randint(1, 10)}",
                    "source_event_id": source_event_id,
                    "generated_at": (now - timedelta(days=days_ago, hours=self.rng.randint(0, 23))).isoformat(),
                    "generator": "scale_test",
                    "generator_version": "1.0",
                    "scale_profile": self.config.name,
                    "seed": 42,
                    "epistemic_basis": epistemic_status,
                }
                
                # For evidence_backed, measured, inferred, unknown - ensure provenance has evidence
                if epistemic_status in ("evidence_backed", "inferred", "unknown"):
                    provenance["evidence_refs"] = [f"evidence-{uuid.uuid4().hex[:8]}" for _ in range(self.rng.randint(1, 3))]
                # For measured - ensure metrics are present
                if epistemic_status == "measured":
                    provenance["measurement_method"] = "automated_sensor"
                    provenance["measurement_precision"] = "high"
                
                # Build metrics JSON - more detailed for measured status
                if epistemic_status == "measured":
                    metrics_json = {
                        "duration_ms": self.rng.randint(1, 5000),
                        "count": self.rng.randint(1, 100),
                        "measurements": [
                            {"name": "latency", "value": self.rng.uniform(10, 500), "unit": "ms"},
                            {"name": "throughput", "value": self.rng.uniform(100, 10000), "unit": "req/s"},
                        ]
                    }
                else:
                    metrics_json = {"duration_ms": self.rng.randint(1, 5000), "count": self.rng.randint(1, 100)}
                
                obs = CanonicalObservation(
                    id=obs_id,
                    organization_id=self.org_id,
                    observation_type=obs_type,
                    fingerprint=fingerprint,
                    source=source,
                    source_component=f"{source}-{self.rng.randint(1, 10)}",
                    actor_id=self.rng.choice(employee_ids) if employee_ids and self.rng.random() < 0.3 else None,
                    actor_type="system",
                    severity=self.rng.choice(severities),
                    epistemic_status=epistemic_status,
                    correlation_id=uuid.uuid4().hex[:32] if self.rng.random() < 0.3 else None,
                    trace_id=uuid.uuid4().hex[:32] if self.rng.random() < 0.2 else None,
                    span_id=None,
                    parent_span_id=None,
                    operation_id=self.rng.choice(operation_ids) if operation_ids and self.rng.random() < 0.2 else None,
                    operation_type=obs_type if self.rng.random() < 0.2 else None,
                    attempt_id=None,
                    integration_id=self.rng.choice(integration_ids) if integration_ids and self.rng.random() < 0.2 else None,
                    connector_id=None,
                    external_operation_id=None,
                    security_event_id=None,
                    degradation_id=None,
                    title=f"Observation {i+1}",
                    description=f"Observation {i+1} description",
                    details_json={"key": f"value_{i}", "metric": self.rng.uniform(0, 100)},
                    metrics_json=metrics_json,
                    provenance_json=provenance,
                    source_event_id=source_event_id,
                    observed_at=now - timedelta(days=days_ago, hours=self.rng.randint(0, 23)),
                    recorded_at=now,
                    duration_ms=self.rng.randint(1, 5000),
                    version=1,
                )
                batch_observations.append(obs)
                observation_ids.append(obs_id)
            
            # Bulk insert using session
            self.db.bulk_save_objects(batch_observations)
            self.db.flush()
        
        self._created_ids["observations"].extend(observation_ids)
        
        return self.config.observation_count
    
    def _generate_correlations(self) -> int:
        corr_types = ["request_flow", "error_trace", "deployment", "incident", "business_transaction"]
        statuses = ["active"] * 30 + ["completed"] * 60 + ["failed"] * 10
        
        count = max(1, self.config.employee_count // 10)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:corr:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            chain = {
                "steps": [
                    {"step_number": 1, "observation_type": "request", "source": "api", "outcome": "success"},
                    {"step_number": 2, "observation_type": "processing", "source": "worker", "outcome": "success"},
                    {"step_number": 3, "observation_type": "response", "source": "api", "outcome": "success"},
                ]
            }
            
            ctx = CorrelationContext(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                correlation_type=self.rng.choice(corr_types),
                correlation_id=uuid.uuid4().hex[:32],
                trace_id=uuid.uuid4().hex[:32],
                chain_json=json.dumps(chain),
                current_step=3,
                total_steps=3,
                status=self.rng.choice(statuses),
                outcome="success",
                fingerprint=fingerprint,
            )
            self.db.add(ctx)
            self._created_ids["correlations"].append(ctx.id)
        
        return count
    
    def _generate_degradations(self) -> int:
        deg_types = ["performance", "availability", "data_quality", "integration", "capacity", "security"]
        severities = ["minor"] * 50 + ["major"] * 35 + ["critical"] * 15
        states = ["detected"] * 10 + ["investigating"] * 20 + ["contained"] * 20 + ["recovering"] * 20 + ["verified"] * 20 + ["learned"] * 10
        
        count = max(1, self.config.employee_count // 100)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:deg:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            # Generate provenance and source_event_id
            source_event_id = f"evt-deg-{uuid.uuid4().hex[:20]}"
            provenance = {
                "source_type": "degradation_detector",
                "source_component": "scale_generator",
                "source_event_id": source_event_id,
                "generated_at": utcnow().isoformat(),
                "generator": "scale_test",
                "generator_version": "1.0",
                "scale_profile": self.config.name,
                "seed": 42,
            }
            
            deg = Degradation(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                degradation_type=self.rng.choice(deg_types),
                severity=self.rng.choice(severities),
                title=f"Degradation {i+1}: {self.rng.choice(deg_types).title()} Issue",
                description=f"Degradation {i+1} description",
                state=self.rng.choice(states),
                details_json=json.dumps({"impact": "medium", "affected_services": ["api", "worker"]}),
                affected_entities_json=json.dumps([{"type": "service", "id": "api-1"}]),
                affected_dimensions_json=json.dumps(["latency", "availability"]),
                detected_at=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)),
                acknowledged_at=utcnow() - timedelta(days=self.rng.randint(0, 30)) if self.rng.random() < 0.8 else None,
                evidence_json=json.dumps([{"type": "metric", "metric": "latency_p99", "threshold": 500, "actual": self.rng.randint(500, 2000)}]),
                provenance_json=provenance,
                fingerprint=fingerprint,
            )
            self.db.add(deg)
            self._created_ids["degradations"].append(deg.id)
        
        return count
    
    def _generate_health_dimensions(self) -> int:
        dimensions = [
            "latency_p99", "error_rate", "throughput", "availability", "cpu_utilization",
            "memory_utilization", "disk_utilization", "queue_depth", "cache_hit_rate",
            "deployment_frequency", "lead_time", "mttr", "change_failure_rate",
            "customer_satisfaction", "employee_satisfaction", "security_posture",
            "compliance_score", "cost_efficiency", "revenue_per_employee",
        ]
        
        scopes = ["company", "department", "team"]
        
        dept_ids = self._created_ids["departments"]
        team_ids = self._created_ids["teams"]
        
        # Create unique combinations
        created_combinations = set()
        
        for i in range(len(dimensions) * 3):  # Multiple snapshots per dimension
            dimension = self.rng.choice(dimensions)
            scope_type = self.rng.choice(scopes)
            
            if scope_type == "department" and dept_ids:
                scope_id = self.rng.choice(dept_ids)
            elif scope_type == "team" and team_ids:
                scope_id = self.rng.choice(team_ids)
            else:
                scope_id = None
            
            # Ensure unique combination
            combo = (dimension, scope_type, scope_id)
            if combo in created_combinations:
                continue
            created_combinations.add(combo)
            
            fingerprint = hashlib.sha256(
                f"{self.org_id}:hdim:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            # Generate provenance
            source_event_id = f"evt-hdim-{uuid.uuid4().hex[:20]}"
            provenance = {
                "source_type": "health_monitor",
                "source_component": "scale_generator",
                "source_event_id": source_event_id,
                "generated_at": utcnow().isoformat(),
                "generator": "scale_test",
                "generator_version": "1.0",
                "scale_profile": self.config.name,
                "seed": 42,
            }
            
            hdim = HealthDimension(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                dimension=dimension,
                scope_type=scope_type,
                scope_id=scope_id,
                status=self.rng.choice(["healthy", "healthy", "healthy", "degraded", "critical"]),
                current_value=self.rng.uniform(0, 100),
                target_value=self.rng.uniform(50, 95),
                threshold_warn=self.rng.uniform(60, 80),
                threshold_critical=self.rng.uniform(80, 95),
                unit=self.rng.choice(["ms", "%", "count", "ratio", "score"]),
                trend=self.rng.choice(["improving", "stable", "degrading", "volatile"]),
                trend_score=self.rng.uniform(-1, 1),
                slo_target=self.rng.uniform(90, 99.9),
                slo_compliance=self.rng.uniform(80, 100),
                recorded_at=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)),
                window_start=utcnow() - timedelta(days=7),
                window_end=utcnow(),
                evidence_json=json.dumps([{"type": "metric", "metric": dimension, "value": self.rng.uniform(0, 100)}]),
                provenance_json=provenance,
                fingerprint=fingerprint,
            )
            self.db.add(hdim)
            self._created_ids["health_dimensions"].append(hdim.id)
        
        return len(created_combinations)
    
    def _generate_slo_targets(self) -> int:
        dimensions = ["latency_p99", "error_rate", "availability", "throughput"]
        for dim in dimensions:
            fingerprint = hashlib.sha256(
                f"{self.org_id}:slo:{dim}:{self.rng.random()}".encode()
            ).hexdigest()
            slo = SLOTarget(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                dimension=dim,
                scope_type="company",
                target_value=self.rng.uniform(0.95, 0.999) if dim != "error_rate" else self.rng.uniform(0.01, 0.1),
                operator="<=" if dim == "error_rate" else ">=",
                unit="%" if dim != "latency_p99" else "ms",
                window_type="rolling",
                window_size="30d",
                status="active",
                current_compliance=self.rng.uniform(80, 100),
                fingerprint=fingerprint,
            )
            self.db.add(slo)
            self._created_ids["slo_targets"].append(slo.id)
        
        return self.config.slo_target_count
    
    def _generate_freshness_checks(self) -> int:
        feed_types = ["integration", "worker", "event", "sync", "projection"]
        statuses = ["fresh"] * 60 + ["delayed"] * 25 + ["stale"] * 10 + ["unknown"] * 5
        integration_ids = self._created_ids["integrations"]
        count = max(1, self.config.integration_count * 2 + self.config.employee_count // 100)
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:freshness:{i}:{self.rng.random()}".encode()
            ).hexdigest()
            fresh = FreshnessCheck(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                feed_type=self.rng.choice(feed_types),
                scope_type="integration" if self.rng.random() < 0.5 else "worker",
                scope_id=self.rng.choice(integration_ids) if integration_ids and self.rng.random() < 0.5 else None,
                feed_id=f"feed_{i}",
                status=self.rng.choice(statuses),
                expected_interval_seconds=self.rng.choice([60, 300, 600, 1800, 3600]),
                last_event_at=utcnow() - timedelta(seconds=self.rng.randint(0, 86400)),
                last_checked_at=utcnow(),
                delay_seconds=self.rng.randint(0, 86400),
                max_acceptable_delay_seconds=self.rng.choice([3600, 7200, 14400, 86400]),
                details_json={"source": "sync_generator"},
                fingerprint=fingerprint,
            )
            self.db.add(fresh)
            self._created_ids["freshness_checks"].append(fresh.id)
        
        return count
    
    def _generate_operational_targets(self) -> int:
        target_types = ["worker_completion", "operation_completion", "recovery_time", "sync_freshness"]
        statuses = ["active"] * 60 + ["paused"] * 10 + ["met"] * 20 + ["missed"] * 10
        units = ["seconds", "ratio", "count"]
        count = max(1, self.config.employee_count // 20)
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:optarget:{i}:{self.rng.random()}".encode()
            ).hexdigest()
            ttype = self.rng.choice(target_types)
            ot = OperationalTarget(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                target_type=ttype,
                scope_type="company",
                target_duration_seconds=self.rng.randint(300, 3600),
                target_value=self.rng.uniform(0.8, 1.0) if ttype != "recovery_time" else self.rng.uniform(0.5, 1.0),
                unit=self.rng.choice(units),
                status=self.rng.choice(statuses),
                current_value=self.rng.uniform(0.5, 1.0),
                window_start=utcnow() - timedelta(days=7),
                window_end=utcnow() + timedelta(days=7),
                metadata_json={"source": "sync_generator"},
                fingerprint=fingerprint,
            )
            self.db.add(ot)
            self._created_ids["operational_targets"].append(ot.id)
        
        return count
    
    def _generate_learning(self) -> int:
        kinds = ["pattern", "anti_pattern", "decision_principle", "process_improvement", "technical_guidance"]
        statuses = ["active"] * 60 + ["superseded"] * 20 + ["archived"] * 20
        lifecycles = ["observed"] * 30 + ["validated"] * 40 + ["institutionalized"] * 30
        
        count = max(1, self.config.employee_count // 20)
        
        for i in range(count):
            fingerprint = hashlib.sha256(
                f"{self.org_id}:learning:{i}:{self.rng.random()}".encode()
            ).hexdigest()[:160]
            
            learning = OrganizationalLearning(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                kind=self.rng.choice(kinds),
                fingerprint=fingerprint,
                title=f"Lesson {i+1}: {self.rng.choice(['Always', 'Never', 'Prefer', 'Avoid', 'Consider'])} {self.rng.choice(['validate input', 'use transactions', 'add indexes', 'monitor latency', 'test edge cases'])}",
                lesson=f"Detailed lesson {i+1}: Based on {self.rng.randint(1, 50)} observations, we learned that...",
                status=self.rng.choice(statuses),
                lifecycle=self.rng.choice(lifecycles),
                confidence=self.rng.uniform(0.5, 0.95),
                topic_name=self.rng.choice(["engineering", "process", "security", "performance", "reliability"]),
                source_type="pattern",
                source_id=None,
                observed_at=utcnow() - timedelta(days=self.rng.randint(0, 365 * self.config.years_of_history)),
            )
            self.db.add(learning)
            self._created_ids["learning"].append(learning.id)
        
        return count
    
    def _generate_attention(self) -> int:
        attn_types = ["degradation", "freshness_stale", "security", "capacity", "slo_breach", "drift", "learning"]
        priorities = ["info"] * 40 + ["watch"] * 30 + ["alert"] * 20 + ["critical"] * 10
        urgencies = ["low"] * 30 + ["normal"] * 40 + ["high"] * 20 + ["critical"] * 10
        statuses = ["open"] * 50 + ["acknowledged"] * 20 + ["in_progress"] * 15 + ["resolved"] * 15
        source_types = ["system", "human", "monitoring", "integration"]
        
        count = max(1, self.config.employee_count // 50)
        
        for i in range(count):
            source_event_id = f"evt-attn-{uuid.uuid4().hex[:20]}"
            
            attn = CompanyAttention(
                id=uuid.uuid4().hex[:32],
                organization_id=self.org_id,
                attention_type=self.rng.choice(attn_types),
                priority=self.rng.choice(priorities),
                title=f"Attention {i+1}: {self.rng.choice(attn_types).replace('_', ' ').title()}",
                description=f"Attention signal {i+1} description",
                source_type=self.rng.choice(source_types),
                source_id=str(i),
                source_event_id=source_event_id,
                priority_score=self.rng.uniform(0, 1),
                urgency=self.rng.choice(urgencies),
                status=self.rng.choice(statuses),
                assigned_to=self.rng.choice(self._created_ids["employees"]) if self._created_ids["employees"] and self.rng.random() < 0.5 else None,
            )
            self.db.add(attn)
            self._created_ids["attention"].append(attn.id)
        
        return count


def run_sync_scale_generation(
    db,
    organization_id: str,
    scale: str = "medium",
    run_metadata: Optional[ScaleRunMetadata] = None,
    state_store: Optional[ScaleRunStateStore] = None,
) -> Dict[str, int]:
    """Run scale data generation for a given scale level (sync version)."""
    if scale not in SCALE_LEVELS:
        raise ValueError(f"Unknown scale: {scale}. Valid: {list(SCALE_LEVELS.keys())}")
    
    config = ScaleConfig(
        name=scale,
        employee_count=SCALE_LEVELS[scale],
    )
    
    generator = SyncScaleGenerator(db, organization_id, config, run_metadata, state_store)
    return generator.generate_all()


def run_sync_universal_scale_generation(
    db,
    organization_id: str,
    profile: UniversalScaleProfile,
    run_metadata: Optional[ScaleRunMetadata] = None,
    state_store: Optional[ScaleRunStateStore] = None,
) -> Dict[str, int]:
    """Run scale data generation using UniversalScaleProfile (35-F)."""
    generator = SyncScaleGenerator(db, organization_id, profile, run_metadata, state_store)
    return generator.generate_all()


def run_multi_tenant_scale_generation(
    db,
    profiles: List[UniversalScaleProfile],
) -> Dict[str, Dict[str, int]]:
    """Run scale data generation for multiple tenants."""
    results = {}
    
    for i, profile in enumerate(profiles):
        # Create organization for this tenant
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name=f"Multi-Tenant Scale Org {profile.name}",
            slug=f"mt-scale-{profile.name}-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            language="en",
            status="active",
        )
        db.add(org)
        db.flush()
        
        results[profile.name] = run_sync_universal_scale_generation(db, org.id, profile)
    
    db.commit()
    return results


# Export
__all__ = [
    "SCALE_LEVELS",
    "ScaleConfig",
    "ScaleDensityStrategy",
    "UniversalScaleProfile",
    "UNIVERSAL_SCALE_PROFILES",
    "ScaleGenerator",
    "SyncScaleGenerator",
    "run_scale_generation",
    "run_sync_scale_generation",
    "run_sync_universal_scale_generation",
    "run_multi_tenant_scale_generation",
    "run_all_scales",
    "get_scale_config",
]