"""Company Experience Configuration — Universal Adaptive Experience Architecture.

These types define the company experience configuration that enables
VCOS to adapt its interface based on organizational complexity.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import String, Text, JSON, ForeignKey, Enum as SQLEnum, Index, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, TimestampMixin, gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyExperienceProfile(str, Enum):
    """Experience profiles based on organizational complexity.

    These are PRESENTATION profiles, NOT separate canonical company models.
    The same canonical company reality is presented differently based on this profile.
    """
    STARTUP = "startup"           # 5-10 employees: Simple, focused, personal
    GROWING = "growing"           # 11-50 employees: Teams, departments emerging
    MID_MARKET = "mid_market"     # 51-500 employees: Departments, managers, workflows
    LARGE_ENTERPRISE = "large_enterprise"  # 501-5000: Multi-dept, governance, regions
    GLOBAL_ENTERPRISE = "global_enterprise"  # 5000+: Multi-entity, regions, subsidiaries


class CompanyExperienceConfig(Base, TimestampMixin):
    """Company experience configuration — adapts the interface to the company's needs.

    This is a configuration layer, NOT a separate company model.
    The canonical company reality (Organization) remains unchanged.
    """

    __tablename__ = "company_experience_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    # Experience profile (determines UI complexity)
    experience_profile: Mapped[CompanyExperienceProfile] = mapped_column(
        SQLEnum(CompanyExperienceProfile), default=CompanyExperienceProfile.STARTUP, nullable=False
    )

    # Company complexity indicators (used to suggest profile, not enforce)
    employee_count: Mapped[int] = mapped_column(default=0)
    organizational_depth: Mapped[int] = mapped_column(default=1)  # hierarchy levels
    organizational_unit_count: Mapped[int] = mapped_column(default=0)
    legal_entity_count: Mapped[int] = mapped_column(default=1)
    geographic_footprint_count: Mapped[int] = mapped_column(default=1)  # countries/regions

    # Governance complexity
    governance_complexity: Mapped[str] = mapped_column(String(20), default="simple")  # simple | standard | complex | delegated | federated
    approval_levels: Mapped[int] = mapped_column(default=1)

    # Integration and workflow complexity
    integration_count: Mapped[int] = mapped_column(default=0)
    workflow_complexity: Mapped[str] = mapped_column(String(20), default="simple")  # simple | conditional | complex

    # Experience preferences (presentation layer, not canonical state)
    enabled_modules: Mapped[List[str]] = mapped_column(JSON, default=list)  # module keys enabled
    default_dashboard_layout: Mapped[str] = mapped_column(String(32), default="startup")  # startup | growing | enterprise | custom
    navigation_density: Mapped[str] = mapped_column(String(20), default="comfortable")  # comfortable | compact | dense
    progressive_disclosure: Mapped[bool] = mapped_column(default=True)
    show_advanced_features: Mapped[bool] = mapped_column(default=False)

    # Localization and accessibility
    default_language: Mapped[str] = mapped_column(String(10), default="en")
    supported_languages: Mapped[List[str]] = mapped_column(JSON, default=["en"])
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    date_format: Mapped[str] = mapped_column(String(20), default="ISO")
    number_format: Mapped[str] = mapped_column(String(20), default="US")

    # Feature flags (capability toggles)
    feature_flags: Mapped[Dict[str, bool]] = mapped_column(JSON, default=dict)

    # Metadata
    configured_by: Mapped[Optional[str]] = mapped_column(String(32))
    configured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_profile_change: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    previous_profile: Mapped[Optional[str]] = mapped_column(String(32))

    # Relationship
    organization: Mapped["Organization"] = relationship(back_populates="experience_config")

    # Profile suggestion logic (can be overridden by admin)
    @property
    def suggested_profile(self) -> "CompanyExperienceProfile":
        """Suggest profile based on complexity indicators."""
        if self.employee_count <= 10:
            return CompanyExperienceProfile.STARTUP
        elif self.employee_count <= 50:
            return CompanyExperienceProfile.GROWING
        elif self.employee_count <= 500:
            return CompanyExperienceProfile.MID_MARKET
        elif self.employee_count <= 5000:
            return CompanyExperienceProfile.LARGE_ENTERPRISE
        else:
            return CompanyExperienceProfile.GLOBAL_ENTERPRISE

    def should_show_module(self, module_key: str) -> bool:
        """Check if a module should be visible based on profile and config."""
        if not self.enabled_modules:
            # Default modules by profile
            startup_modules = {"home", "workspace", "my-work", "my-day", "company-home", "ai"}
            growing_modules = startup_modules | {"projects", "tasks", "goals", "departments", "teams", "people", "decisions"}
            enterprise_modules = growing_modules | {"finance", "hr", "enterprise", "governance", "intelligence", "twin"}

            if self.experience_profile == CompanyExperienceProfile.STARTUP:
                return module_key in startup_modules
            elif self.experience_profile in (CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET):
                return module_key in growing_modules
            elif self.experience_profile in (CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE):
                return module_key in enterprise_modules

        # If explicitly configured, use that
        return module_key in self.enabled_modules


class CompanyExperienceProfileHistory(Base, TimestampMixin):
    """Audit trail for experience profile changes."""

    __tablename__ = "company_experience_profile_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    previous_profile: Mapped[Optional[str]] = mapped_column(String(32))
    new_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(String(32))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    organization: Mapped["Organization"] = relationship(back_populates="experience_profile_history")


# Profile capability matrix — defines what's available per profile
PROFILE_CAPABILITY_MATRIX: Dict[str, Dict[str, Any]] = {
    "startup": {
        "modules": ["home", "workspace", "my-work", "my-day", "company-home", "ai"],
        "navigation_groups": ["workspace", "ai"],
        "max_org_depth": 1,
        "max_departments": 3,
        "max_teams": 2,
        "governance_level": "simple",
        "approval_levels": 1,
        "modules_enabled_by_default": ["home", "workspace", "my-work", "my-day", "company-home", "ai"],
    },
    "growing": {
        "modules": ["home", "workspace", "my-work", "my-day", "company-home", "ai", "projects", "tasks", "goals", "departments", "teams", "people", "decisions"],
        "navigation_groups": ["workspace", "people", "work", "ai", "knowledge"],
        "max_org_depth": 2,
        "max_departments": 10,
        "max_teams": 10,
        "governance_level": "standard",
        "approval_levels": 2,
        "modules_enabled_by_default": ["home", "workspace", "my-work", "my-day", "company-home", "ai", "projects", "tasks", "goals"],
    },
    "mid_market": {
        "modules": ["home", "workspace", "my-work", "my-day", "company-home", "ai", "projects", "tasks", "goals", "departments", "teams", "people", "decisions", "approvals", "hr", "finance", "customers", "intelligence", "knowledge"],
        "navigation_groups": ["workspace", "people", "work", "customers", "finance", "hr", "intelligence", "knowledge", "governance"],
        "max_org_depth": 3,
        "max_departments": 50,
        "max_teams": 50,
        "governance_level": "standard",
        "approval_levels": 3,
        "modules_enabled_by_default": ["home", "workspace", "my-work", "my-day", "company-home", "ai", "projects", "tasks", "goals", "departments", "teams", "people", "decisions", "approvals"],
    },
    "large_enterprise": {
        "modules": ["all"],
        "navigation_groups": ["workspace", "people", "work", "customers", "operations", "intelligence", "knowledge", "governance", "platform", "administration"],
        "max_org_depth": 5,
        "max_departments": 200,
        "max_teams": 200,
        "governance_level": "delegated",
        "approval_levels": 5,
        "modules_enabled_by_default": ["all"],
    },
    "global_enterprise": {
        "modules": ["all"],
        "navigation_groups": ["all"],
        "max_org_depth": 10,
        "max_departments": 1000,
        "max_teams": 1000,
        "governance_level": "federated",
        "approval_levels": 10,
        "modules_enabled_by_default": ["all"],
        "features": ["multi_entity", "data_residency", "sovereign_deployment", "localization", "advanced_compliance"],
    },
}


def get_profile_capabilities(profile: CompanyExperienceProfile) -> Dict[str, Any]:
    """Get capability matrix for a profile."""
    return PROFILE_CAPABILITY_MATRIX.get(profile, PROFILE_CAPABILITY_MATRIX[CompanyExperienceProfile.STARTUP])


def resolve_experience_profile(
    employee_count: Optional[int] = 0,
    org_depth: Optional[int] = 1,
    org_unit_count: Optional[int] = 0,
    legal_entity_count: Optional[int] = 1,
    geo_count: Optional[int] = 1,
    governance_level: str = "simple",
    workflow_complexity: str = "simple",
) -> CompanyExperienceProfile:
    """Resolve experience profile from complexity indicators.

    This is a suggestion — admin can override.
    """
    # Handle None values
    employee_count = employee_count or 0
    org_depth = org_depth or 1
    org_unit_count = org_unit_count or 0
    legal_entity_count = legal_entity_count or 1
    geo_count = geo_count or 1

    # Weighted scoring
    score = 0
    score += min(employee_count / 10, 50)  # up to 50 points
    score += min(org_depth * 5, 25)  # up to 25 points
    score += min(org_unit_count / 5, 25)  # up to 25 points
    score += min((legal_entity_count - 1) * 10, 20)  # up to 20 points
    score += min((geo_count - 1) * 10, 15)  # up to 15 points

    governance_scores = {"simple": 0, "standard": 15, "complex": 30, "delegated": 25, "federated": 40}
    score += governance_scores.get(governance_level, 0)

    workflow_scores = {"simple": 0, "conditional": 10, "complex": 20}
    score += workflow_scores.get(workflow_complexity, 0)

    if score <= 30:
        return CompanyExperienceProfile.STARTUP
    elif score <= 60:
        return CompanyExperienceProfile.GROWING
    elif score <= 100:
        return CompanyExperienceProfile.MID_MARKET
    elif score <= 180:
        return CompanyExperienceProfile.LARGE_ENTERPRISE
    else:
        return CompanyExperienceProfile.GLOBAL_ENTERPRISE