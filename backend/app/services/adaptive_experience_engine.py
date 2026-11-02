"""Adaptive Experience Engine — Universal Adaptive Company Experience.

This is the core intelligence layer that makes VCOS automatically adapt its
interface, navigation, workspaces, and capabilities based on:

- Company size, industry, organizational complexity
- User roles, permissions, and context
- Geographic context and data residency
- Company Brain insights (what changed, predictions, risks)
- Digital Twin state (capacity, bottlenecks, scenarios)
- Longitudinal reality (35-I) - temporal truth and causality
- Governed autonomy boundaries
- Company continuity requirements

CRITICAL: This engine NEVER grants permissions. It only adapts PRESENTATION.
Backend authorization (RLS, permission service) remains the single authority.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.company_experience import (
    CompanyExperienceConfig,
    CompanyExperienceProfile,
    CompanyExperienceProfileHistory,
    resolve_experience_profile,
    get_profile_capabilities,
    PROFILE_CAPABILITY_MATRIX,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.services.company_experience_service import company_experience_service

logger = logging.getLogger("vcos.adaptive_experience")


class UserContextRole(str, Enum):
    """User context roles for adaptive presentation."""
    EMPLOYEE = "employee"
    MANAGER = "manager"
    EXECUTIVE = "executive"
    ADMIN = "admin"
    DEVELOPER = "developer"
    HR = "hr"
    FINANCE = "finance"
    CUSTOMER_FACING = "customer_facing"


class GeographicContext(str, Enum):
    """Geographic contexts for data residency and localization."""
    AMERICAS = "americas"
    EMEA = "emea"
    APAC = "apac"
    GLOBAL = "global"
    SOVEREIGN = "sovereign"  # Data residency required


@dataclass
class AdaptiveContext:
    """Complete context for adaptive experience resolution."""
    organization_id: str
    user_id: str
    user_role: UserContextRole
    user_permissions: Set[str]
    geographic_context: GeographicContext = GeographicContext.GLOBAL
    current_page: Optional[str] = None
    current_task: Optional[str] = None
    time_of_day: Optional[str] = None  # morning, afternoon, evening
    device_type: str = "desktop"  # desktop, mobile, tablet
    accessibility_needs: List[str] = field(default_factory=list)
    # Company Brain signals
    recent_changes: List[Dict[str, Any]] = field(default_factory=list)
    active_predictions: List[Dict[str, Any]] = field(default_factory=list)
    active_risks: List[Dict[str, Any]] = field(default_factory=list)
    # Digital Twin signals
    capacity_utilization: float = 0.0
    bottlenecks: List[str] = field(default_factory=list)
    scenario_mode: bool = False
    # Longitudinal context
    temporal_scope: str = "current"  # current, historical, projected
    causality_chain: List[str] = field(default_factory=list)


@dataclass
class AdaptiveModule:
    """A module with adaptive presentation properties."""
    key: str
    label: str
    icon: str
    description: str
    required_permissions: List[str] = field(default_factory=list)
    profile_requirements: List[CompanyExperienceProfile] = field(default_factory=list)
    role_affinity: Dict[UserContextRole, float] = field(default_factory=dict)
    geographic_availability: List[GeographicContext] = field(default_factory=lambda: [GeographicContext.GLOBAL])
    feature_flag: Optional[str] = None
    # Adaptive properties
    priority: int = 50  # 0-100, higher = more prominent
    conditional_visibility: Optional[str] = None  # expression for conditional show
    progressive_disclosure: bool = True  # hide in progressive mode
    badge_count: int = 0
    badge_label: Optional[str] = None


@dataclass
class AdaptiveNavigationGroup:
    """A navigation group with adaptive properties."""
    key: str
    label: str
    modules: List[AdaptiveModule]
    profile_requirements: List[CompanyExperienceProfile] = field(default_factory=list)
    role_affinity: Dict[UserContextRole, float] = field(default_factory=dict)
    priority: int = 50
    collapsible: bool = True
    default_collapsed: bool = False


@dataclass
class AdaptiveWorkspaceConfig:
    """Complete adaptive workspace configuration."""
    profile: CompanyExperienceProfile
    navigation_groups: List[AdaptiveNavigationGroup]
    visible_modules: List[str]
    dashboard_layout: str
    navigation_density: str
    progressive_disclosure: bool
    show_advanced_features: bool
    feature_flags: Dict[str, bool]
    # Intelligence overlays
    company_brain_insights: Dict[str, Any] = field(default_factory=dict)
    digital_twin_overlay: Dict[str, Any] = field(default_factory=dict)
    recommended_actions: List[Dict[str, Any]] = field(default_factory=list)
    # Metadata
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context_fingerprint: str = ""


# Module registry with adaptive properties
MODULE_REGISTRY: Dict[str, AdaptiveModule] = {
    # Core modules (always available)
    "home": AdaptiveModule(
        key="home",
        label="Home",
        icon="Home",
        description="Personal landing page",
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 0.8, 
                      UserContextRole.EXECUTIVE: 0.6, UserContextRole.ADMIN: 0.5},
        priority=100,
        progressive_disclosure=False,
    ),
    "workspace": AdaptiveModule(
        key="workspace",
        label="Workspace",
        icon="LayoutGrid",
        description="Unified operating surface",
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 0.8, UserContextRole.ADMIN: 0.7},
        priority=95,
        progressive_disclosure=False,
    ),
    "my-work": AdaptiveModule(
        key="my-work",
        label="My Work",
        icon="ListTodo",
        description="Tasks and commitments assigned to you",
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.5},
        priority=90,
        progressive_disclosure=False,
    ),
    "my-day": AdaptiveModule(
        key="my-day",
        label="My Day",
        icon="Sun",
        description="Daily operating surface",
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.6},
        priority=90,
        progressive_disclosure=False,
    ),
    "company-home": AdaptiveModule(
        key="company-home",
        label="Company Home",
        icon="Building2",
        description="Executive operating surface",
        required_permissions=["executive:view", "workspace:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.MANAGER: 0.7, 
                      UserContextRole.ADMIN: 0.8},
        priority=85,
        progressive_disclosure=True,
    ),
    "ai": AdaptiveModule(
        key="ai",
        label="AI Companion",
        icon="Sparkles",
        description="Conversational AI for work",
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 1.0, UserContextRole.ADMIN: 1.0,
                      UserContextRole.DEVELOPER: 1.0},
        priority=95,
        progressive_disclosure=False,
        feature_flag="ai_companion_enabled",
    ),
    "company-brain": AdaptiveModule(
        key="company-brain",
        label="Company Brain",
        icon="Brain",
        description="Organizational intelligence and insights",
        required_permissions=["brain:read"],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.MANAGER: 0.8, 
                      UserContextRole.ADMIN: 0.9},
        priority=80,
        progressive_disclosure=True,
        feature_flag="company_brain_enabled",
    ),
    
    # People modules
    "people": AdaptiveModule(
        key="people",
        label="People",
        icon="Users",
        description="Employee directory and profiles",
        required_permissions=["employees:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.7, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 0.8, UserContextRole.HR: 1.0},
        priority=75,
        progressive_disclosure=True,
    ),
    "departments": AdaptiveModule(
        key="departments",
        label="Departments",
        icon="Building2",
        description="Department structure and management",
        required_permissions=["departments:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.MANAGER: 1.0, UserContextRole.EXECUTIVE: 0.9, 
                      UserContextRole.HR: 1.0, UserContextRole.ADMIN: 0.8},
        priority=70,
        progressive_disclosure=True,
    ),
    "teams": AdaptiveModule(
        key="teams",
        label="Teams",
        icon="UserSquare2",
        description="Team management and collaboration",
        required_permissions=["teams:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.MANAGER: 1.0, UserContextRole.EMPLOYEE: 0.8, 
                      UserContextRole.EXECUTIVE: 0.7},
        priority=70,
        progressive_disclosure=True,
    ),
    
    # Work modules
    "projects": AdaptiveModule(
        key="projects",
        label="Projects",
        icon="FolderKanban",
        description="Project portfolio and execution",
        required_permissions=["projects:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.9, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 0.8},
        priority=85,
        progressive_disclosure=True,
    ),
    "tasks": AdaptiveModule(
        key="tasks",
        label="Tasks",
        icon="CheckSquare2",
        description="Task management and tracking",
        required_permissions=["tasks:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.5},
        priority=80,
        progressive_disclosure=True,
    ),
    "goals": AdaptiveModule(
        key="goals",
        label="Goals",
        icon="Target",
        description="OKRs and strategic objectives",
        required_permissions=["goals:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.MANAGER: 1.0, UserContextRole.EXECUTIVE: 1.0, 
                      UserContextRole.EMPLOYEE: 0.7},
        priority=75,
        progressive_disclosure=True,
    ),
    "approvals": AdaptiveModule(
        key="approvals",
        label="Approvals",
        icon="Stamp",
        description="Approval workflows and requests",
        required_permissions=["approvals:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.MANAGER: 1.0, UserContextRole.EXECUTIVE: 0.8, 
                      UserContextRole.EMPLOYEE: 0.6},
        priority=70,
        progressive_disclosure=True,
    ),
    "risks": AdaptiveModule(
        key="risks",
        label="Risks",
        icon="ShieldAlert",
        description="Risk identification and management",
        required_permissions=["risks:read"],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.ADMIN: 0.8},
        priority=75,
        progressive_disclosure=True,
    ),
    "calendar": AdaptiveModule(
        key="calendar",
        label="Calendar",
        icon="CalendarDays",
        description="Schedule and meeting management",
        required_permissions=["calendar:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 0.9},
        priority=80,
        progressive_disclosure=True,
    ),
    
    # Customers
    "customers": AdaptiveModule(
        key="customers",
        label="Customers",
        icon="Handshake",
        description="Customer relationship management",
        required_permissions=["crm:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.CUSTOMER_FACING: 1.0, UserContextRole.MANAGER: 0.8, 
                      UserContextRole.EXECUTIVE: 0.7},
        priority=70,
        progressive_disclosure=True,
    ),
    
    # Finance
    "finance": AdaptiveModule(
        key="finance",
        label="Finance",
        icon="Banknote",
        description="Financial management and reporting",
        required_permissions=["finance:read"],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.FINANCE: 1.0, UserContextRole.EXECUTIVE: 0.9, 
                      UserContextRole.ADMIN: 0.7},
        priority=65,
        progressive_disclosure=True,
    ),
    
    # HR
    "hr": AdaptiveModule(
        key="hr",
        label="People Operations",
        icon="Users",
        description="HR management and operations",
        required_permissions=["hr:read"],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.HR: 1.0, UserContextRole.MANAGER: 0.7, 
                      UserContextRole.EXECUTIVE: 0.6},
        priority=65,
        progressive_disclosure=True,
    ),
    
    # Intelligence
    "intelligence": AdaptiveModule(
        key="intelligence",
        label="Background Intelligence",
        icon="Brain",
        description="Automated intelligence and insights",
        required_permissions=["intelligence:read"],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.ADMIN: 0.8},
        priority=60,
        progressive_disclosure=True,
        feature_flag="background_intelligence_enabled",
    ),
    
    # Digital Twin
    "twin": AdaptiveModule(
        key="twin",
        label="Digital Twin",
        icon="Activity",
        description="Company simulation and scenarios",
        required_permissions=["digital_twin:read"],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.ADMIN: 0.8},
        priority=55,
        progressive_disclosure=True,
        feature_flag="digital_twin_enabled",
    ),
    
    # Knowledge
    "knowledge": AdaptiveModule(
        key="knowledge",
        label="Knowledge Hub",
        icon="FileText",
        description="Documents, wiki, and decisions",
        required_permissions=["knowledge:read"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.8, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.7},
        priority=70,
        progressive_disclosure=True,
    ),
    
    # Governance
    "governance": AdaptiveModule(
        key="governance",
        label="Governance",
        icon="ShieldCheck",
        description="Governance and compliance",
        required_permissions=["governance:read"],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.ADMIN: 1.0, 
                      UserContextRole.MANAGER: 0.6},
        priority=60,
        progressive_disclosure=True,
    ),
    
    # Platform/Enterprise
    "enterprise": AdaptiveModule(
        key="enterprise",
        label="Enterprise Console",
        icon="Building2",
        description="Platform administration",
        required_permissions=["enterprise:read"],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.ADMIN: 1.0, UserContextRole.EXECUTIVE: 0.5},
        priority=50,
        progressive_disclosure=True,
    ),
    
    # Developer
    "developers": AdaptiveModule(
        key="developers",
        label="Developer Portal",
        icon="Boxes",
        description="Applications, agents, and integrations",
        required_permissions=["developers:read"],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.DEVELOPER: 1.0, UserContextRole.ADMIN: 0.8},
        priority=55,
        progressive_disclosure=True,
    ),
    
    # Learning
    "learning": AdaptiveModule(
        key="learning",
        label="Learning Center",
        icon="BookOpen",
        description="Courses, skills, and career development",
        required_permissions=["learning:read"],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.8, UserContextRole.MANAGER: 0.7, 
                      UserContextRole.HR: 1.0},
        priority=60,
        progressive_disclosure=True,
    ),
    
    # Community
    "community": AdaptiveModule(
        key="community",
        label="Community",
        icon="Users",
        description="Feed, forums, and collaboration",
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.9, UserContextRole.MANAGER: 0.7, 
                      UserContextRole.EXECUTIVE: 0.5},
        priority=65,
        progressive_disclosure=True,
    ),
    
    # Search
    "search": AdaptiveModule(
        key="search",
        label="Universal Search",
        icon="Search",
        description="Search across all canonical reality",
        required_permissions=["search:global"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.8, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.8, UserContextRole.ADMIN: 0.9},
        priority=75,
        progressive_disclosure=True,
    ),
    
    # Command
    "command": AdaptiveModule(
        key="command",
        label="Ask VCOS",
        icon="Command",
        description="Natural language command interface",
        required_permissions=["workspace:command"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.9, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 0.9},
        priority=80,
        progressive_disclosure=True,
    ),
    
    # Admin
    "admin": AdaptiveModule(
        key="admin",
        label="Administration",
        icon="Settings",
        description="System administration",
        required_permissions=["organization:update", "users:manage"],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.ADMIN: 1.0},
        priority=40,
        progressive_disclosure=True,
    ),
}


# Navigation group definitions
NAVIGATION_GROUPS: Dict[str, AdaptiveNavigationGroup] = {
    "workspace": AdaptiveNavigationGroup(
        key="workspace",
        label="Workspace",
        modules=[MODULE_REGISTRY[k] for k in ["home", "workspace", "my-work", "my-day"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        priority=100,
        default_collapsed=False,
    ),
    "ai": AdaptiveNavigationGroup(
        key="ai",
        label="AI",
        modules=[MODULE_REGISTRY[k] for k in ["ai", "company-brain"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 1.0, UserContextRole.MANAGER: 1.0, 
                      UserContextRole.EXECUTIVE: 1.0, UserContextRole.DEVELOPER: 1.0},
        priority=95,
        default_collapsed=False,
    ),
    "people": AdaptiveNavigationGroup(
        key="people",
        label="People",
        modules=[MODULE_REGISTRY[k] for k in ["people", "departments", "teams"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.MANAGER: 1.0, UserContextRole.HR: 1.0, 
                      UserContextRole.EXECUTIVE: 0.9, UserContextRole.EMPLOYEE: 0.6},
        priority=80,
    ),
    "work": AdaptiveNavigationGroup(
        key="work",
        label="Work",
        modules=[MODULE_REGISTRY[k] for k in ["projects", "tasks", "goals", "approvals", "calendar", "risks"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.MANAGER: 1.0, UserContextRole.EMPLOYEE: 0.9, 
                      UserContextRole.EXECUTIVE: 0.7},
        priority=85,
    ),
    "customers": AdaptiveNavigationGroup(
        key="customers",
        label="Customers",
        modules=[MODULE_REGISTRY[k] for k in ["customers"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.CUSTOMER_FACING: 1.0, UserContextRole.MANAGER: 0.8, 
                      UserContextRole.EXECUTIVE: 0.7},
        priority=70,
    ),
    "finance": AdaptiveNavigationGroup(
        key="finance",
        label="Finance",
        modules=[MODULE_REGISTRY[k] for k in ["finance"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.FINANCE: 1.0, UserContextRole.EXECUTIVE: 0.9, 
                      UserContextRole.ADMIN: 0.7},
        priority=60,
    ),
    "hr": AdaptiveNavigationGroup(
        key="hr",
        label="People Operations",
        modules=[MODULE_REGISTRY[k] for k in ["hr"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.HR: 1.0, UserContextRole.MANAGER: 0.7, 
                      UserContextRole.EXECUTIVE: 0.6},
        priority=55,
    ),
    "intelligence": AdaptiveNavigationGroup(
        key="intelligence",
        label="Intelligence",
        modules=[MODULE_REGISTRY[k] for k in ["intelligence", "twin"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.ADMIN: 0.9},
        priority=50,
    ),
    "knowledge": AdaptiveNavigationGroup(
        key="knowledge",
        label="Knowledge",
        modules=[MODULE_REGISTRY[k] for k in ["knowledge", "learning"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.8, UserContextRole.MANAGER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.7, UserContextRole.HR: 0.9},
        priority=65,
    ),
    "community": AdaptiveNavigationGroup(
        key="community",
        label="Community",
        modules=[MODULE_REGISTRY[k] for k in ["community"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING, 
                              CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE,
                              CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EMPLOYEE: 0.9, UserContextRole.MANAGER: 0.7, 
                      UserContextRole.EXECUTIVE: 0.5},
        priority=60,
    ),
    "governance": AdaptiveNavigationGroup(
        key="governance",
        label="Governance",
        modules=[MODULE_REGISTRY[k] for k in ["governance"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.EXECUTIVE: 1.0, UserContextRole.ADMIN: 1.0, 
                      UserContextRole.MANAGER: 0.6},
        priority=45,
    ),
    "platform": AdaptiveNavigationGroup(
        key="platform",
        label="Platform",
        modules=[MODULE_REGISTRY[k] for k in ["enterprise", "developers"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.ADMIN: 1.0, UserContextRole.DEVELOPER: 0.9, 
                      UserContextRole.EXECUTIVE: 0.5},
        priority=40,
    ),
    "admin": AdaptiveNavigationGroup(
        key="admin",
        label="Administration",
        modules=[MODULE_REGISTRY[k] for k in ["admin"] if k in MODULE_REGISTRY],
        profile_requirements=[CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET,
                              CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE],
        role_affinity={UserContextRole.ADMIN: 1.0},
        priority=30,
        default_collapsed=True,
    ),
}


class AdaptiveExperienceEngine:
    def __init__(self):
        self._profile_transition_thresholds = {
            CompanyExperienceProfile.STARTUP: {"employee_count": 10, "org_depth": 2},
            CompanyExperienceProfile.GROWING: {"employee_count": 50, "org_depth": 3},
            CompanyExperienceProfile.MID_MARKET: {"employee_count": 500, "org_depth": 4},
            CompanyExperienceProfile.LARGE_ENTERPRISE: {"employee_count": 5000, "org_depth": 5},
            CompanyExperienceProfile.GLOBAL_ENTERPRISE: {"employee_count": 10000, "org_depth": 10},
        }

    async def resolve_adaptive_experience(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
    ) -> AdaptiveWorkspaceConfig:
        """
        Resolve the complete adaptive experience for a user in context.
        
        This is the main entry point that integrates all signals and produces
        the adaptive workspace configuration.
        """
        # Get organization and experience config
        org = await db.get(Organization, context.organization_id)
        if not org:
            raise ValueError(f"Organization {context.organization_id} not found")
        
        config = await company_experience_service.get_or_create_experience_config(db, context.organization_id)
        profile = config.experience_profile
        
        # Get profile capabilities
        caps = get_profile_capabilities(profile)
        
        # Check for automatic profile transition
        suggested_profile = await self._check_auto_transition(db, org, config)
        if suggested_profile != profile:
            # Auto-transition if significant growth detected
            logger.info(f"Auto-transition suggested: {profile.value} -> {suggested_profile.value}")
            profile = suggested_profile
            caps = get_profile_capabilities(profile)
        
        # Build adaptive navigation groups
        nav_groups = await self._build_adaptive_navigation(db, context, profile, caps)
        
        # Determine visible modules
        visible_modules = await self._resolve_visible_modules(db, context, profile, caps, nav_groups)
        
        # Get Company Brain insights for this context
        brain_insights = await self._get_company_brain_insights(db, context)
        
        # Get Digital Twin overlay
        twin_overlay = await self._get_digital_twin_overlay(db, context)
        
        # Generate recommended actions based on context
        recommended_actions = await self._generate_recommended_actions(db, context, brain_insights, twin_overlay)
        
        # Build context fingerprint for caching
        context_fingerprint = self._compute_context_fingerprint(context, profile)
        
        return AdaptiveWorkspaceConfig(
            profile=profile,
            navigation_groups=nav_groups,
            visible_modules=visible_modules,
            dashboard_layout=config.default_dashboard_layout,
            navigation_density=config.navigation_density,
            progressive_disclosure=config.progressive_disclosure,
            show_advanced_features=config.show_advanced_features,
            feature_flags=config.feature_flags or {},
            company_brain_insights=brain_insights,
            digital_twin_overlay=twin_overlay,
            recommended_actions=recommended_actions,
            context_fingerprint=context_fingerprint,
        )

    async def _check_auto_transition(
        self,
        db: AsyncSession,
        org: Organization,
        config: CompanyExperienceConfig,
    ) -> CompanyExperienceProfile:
        """Check if organization should auto-transition to a new profile."""
        current_profile = config.experience_profile
        
        # Don't auto-transition if manually configured recently
        if config.last_profile_change:
            days_since_change = (utcnow() - config.last_profile_change).days
            if days_since_change < 30:  # Cooldown period
                return current_profile
        
        # Calculate suggested profile
        suggested = resolve_experience_profile(
            employee_count=org.employee_count,
            org_depth=org.organizational_depth,
            org_unit_count=org.organizational_unit_count,
            legal_entity_count=org.legal_entity_count,
            geo_count=org.geographic_footprint_count,
            governance_level=org.governance_complexity,
            workflow_complexity=org.workflow_complexity,
        )
        
        # Only transition up, never down automatically
        profile_order = {
            CompanyExperienceProfile.STARTUP: 0,
            CompanyExperienceProfile.GROWING: 1,
            CompanyExperienceProfile.MID_MARKET: 2,
            CompanyExperienceProfile.LARGE_ENTERPRISE: 3,
            CompanyExperienceProfile.GLOBAL_ENTERPRISE: 4,
        }
        
        if profile_order[suggested] > profile_order[current_profile]:
            # Verify thresholds are met
            thresholds = self._profile_transition_thresholds.get(suggested, {})
            meets_threshold = True
            if "employee_count" in thresholds and org.employee_count < thresholds["employee_count"]:
                meets_threshold = False
            if "org_depth" in thresholds and org.organizational_depth < thresholds["org_depth"]:
                meets_threshold = False
            
            if meets_threshold:
                # Perform transition
                from app.events.publisher import publish_event
                await company_experience_service.transition_profile(
                    db, org.id, suggested, "system", "system",
                    reason=f"Automatic transition based on growth: {org.employee_count} employees, depth {org.organizational_depth}"
                )
                return suggested
        
        return current_profile

    async def _build_adaptive_navigation(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
        profile: CompanyExperienceProfile,
        caps: Dict[str, Any],
    ) -> List[AdaptiveNavigationGroup]:
        """Build navigation groups adapted to profile, role, and context."""
        # Get profile navigation groups
        profile_nav_groups = caps.get("navigation_groups", ["workspace", "ai"])
        
        visible_groups = []
        for group_key in profile_nav_groups:
            if group_key not in NAVIGATION_GROUPS:
                continue
            
            group = NAVIGATION_GROUPS[group_key]
            
            # Check profile requirement
            if profile not in group.profile_requirements:
                continue
            
            # Check role affinity
            role_score = group.role_affinity.get(context.user_role, 0.5)
            if role_score < 0.3:
                continue
            
            # Filter modules within group
            visible_modules = []
            for module in group.modules:
                if await self._is_module_visible(db, context, profile, module):
                    visible_modules.append(module)
            
            if not visible_modules:
                continue
            
            # Sort modules by priority and role affinity
            visible_modules.sort(key=lambda m: (
                -m.priority,
                -m.role_affinity.get(context.user_role, 0.5)
            ))
            
            visible_groups.append(AdaptiveNavigationGroup(
                key=group.key,
                label=group.label,
                modules=visible_modules,
                profile_requirements=group.profile_requirements,
                role_affinity=group.role_affinity,
                priority=group.priority,
                collapsible=group.collapsible,
                default_collapsed=group.default_collapsed,
            ))
        
        # Sort groups by priority
        visible_groups.sort(key=lambda g: -g.priority)
        
        return visible_groups

    async def _is_module_visible(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
        profile: CompanyExperienceProfile,
        module: AdaptiveModule,
    ) -> bool:
        """Determine if a module should be visible in the current context."""
        # Check profile requirement
        if profile not in module.profile_requirements:
            return False
        
        # Check geographic availability
        if context.geographic_context not in module.geographic_availability:
            if GeographicContext.GLOBAL not in module.geographic_availability:
                return False
        
        # Check feature flag
        if module.feature_flag:
            config = await company_experience_service.get_experience_config(db, context.organization_id)
            if config and not config.feature_flags.get(module.feature_flag, False):
                return False
        
        # Check permissions
        if module.required_permissions:
            has_permission = any(p in context.user_permissions for p in module.required_permissions)
            if not has_permission:
                return False
        
        # Check progressive disclosure
        if module.progressive_disclosure:
            config = await company_experience_service.get_experience_config(db, context.organization_id)
            if config and config.progressive_disclosure:
                # In progressive mode, only show high-priority modules for the role
                role_score = module.role_affinity.get(context.user_role, 0.5)
                if role_score < 0.7 and module.priority < 80:
                    return False
        
        # Check conditional visibility
        if module.conditional_visibility:
            # Would evaluate expression in production
            pass
        
        return True

    async def _resolve_visible_modules(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
        profile: CompanyExperienceProfile,
        caps: Dict[str, Any],
        nav_groups: List[AdaptiveNavigationGroup],
    ) -> List[str]:
        """Resolve the complete list of visible module keys."""
        visible = set()
        
        # Add modules from navigation groups
        for group in nav_groups:
            for module in group.modules:
                visible.add(module.key)
        
        # Add profile default modules
        default_modules = caps.get("modules_enabled_by_default", [])
        visible.update(default_modules)
        
        # Add explicitly enabled modules from config
        config = await company_experience_service.get_experience_config(db, context.organization_id)
        if config and config.enabled_modules:
            visible.update(config.enabled_modules)
        
        return list(visible)

    async def _get_company_brain_insights(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
    ) -> Dict[str, Any]:
        """Get Company Brain insights for adaptive experience."""
        try:
            from app.intelligence.company_brain import company_brain
            from app.models.user import User
            
            # Get user if available
            user = None
            if context.user_id:
                user = await db.get(User, context.user_id)
            
            if not user:
                return {}
            
            # Get overview from Company Brain
            overview = await company_brain.overview(db, context.organization_id, user=user)
            
            # Get what changed recently
            changes = await company_brain.what_changed(
                db, context.organization_id, user=user, days=7
            )
            
            return {
                "overview": overview,
                "recent_changes": changes.get("changes", [])[:10],
                "change_count": len(changes.get("changes", [])),
            }
        except Exception as e:
            logger.warning(f"Failed to get Company Brain insights: {e}")
            return {}

    async def _get_digital_twin_overlay(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
    ) -> Dict[str, Any]:
        """Get Digital Twin state for adaptive overlay."""
        try:
            from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
            from app.intelligence.company_context import resolve_caller_access
            from app.models.user import User
            
            # Get user if available
            user = None
            if context.user_id:
                user = await db.get(User, context.user_id)
            
            if not user:
                return {}
            
            caller = await resolve_caller_access(db, organization_id=context.organization_id, user=user)
            if caller:
                twin_state = await canonical_digital_twin_service.derive_twin_state(
                    db, caller=caller, scope_type="org", scope_id=context.organization_id
                )
                return {
                    "health_score": twin_state.health_score if hasattr(twin_state, 'health_score') else 0,
                    "capacity_utilization": twin_state.utilization if hasattr(twin_state, 'utilization') else 0,
                    "bottlenecks": twin_state.overloaded_capabilities if hasattr(twin_state, 'overloaded_capabilities') else [],
                    "active_scenarios": twin_state.active_scenarios if hasattr(twin_state, 'active_scenarios') else 0,
                }
        except Exception as e:
            logger.warning(f"Failed to get Digital Twin overlay: {e}")
        return {}

    async def _generate_recommended_actions(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
        brain_insights: Dict[str, Any],
        twin_overlay: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate context-aware recommended actions."""
        actions = []
        
        # From Company Brain changes
        for change in brain_insights.get("recent_changes", [])[:3]:
            actions.append({
                "type": "review_change",
                "label": f"Review: {change.get('description', 'Recent change')}",
                "action": "navigate",
                "target": "/brain/what-changed",
                "priority": 80,
                "source": "company_brain",
            })
        
        # From Digital Twin bottlenecks
        for bottleneck in twin_overlay.get("bottlenecks", [])[:2]:
            actions.append({
                "type": "resolve_bottleneck",
                "label": f"Address bottleneck: {bottleneck}",
                "action": "navigate",
                "target": "/twin?tab=health",
                "priority": 85,
                "source": "digital_twin",
            })
        
        # From capacity utilization
        utilization = twin_overlay.get("capacity_utilization", 0)
        if utilization > 90:
            actions.append({
                "type": "capacity_alert",
                "label": f"Capacity critical at {utilization}%",
                "action": "navigate",
                "target": "/workspace?tab=capacity",
                "priority": 90,
                "source": "digital_twin",
            })
        elif utilization > 75:
            actions.append({
                "type": "capacity_warning",
                "label": f"Capacity high at {utilization}%",
                "action": "navigate",
                "target": "/workspace?tab=capacity",
                "priority": 70,
                "source": "digital_twin",
            })
        
        # Role-specific recommendations
        if context.user_role == UserContextRole.MANAGER:
            actions.append({
                "type": "team_review",
                "label": "Review team capacity and commitments",
                "action": "navigate",
                "target": "/workspace?tab=manager",
                "priority": 75,
                "source": "role_context",
            })
        elif context.user_role == UserContextRole.EXECUTIVE:
            actions.append({
                "type": "executive_briefing",
                "label": "View executive briefing",
                "action": "navigate",
                "target": "/brain/brief",
                "priority": 80,
                "source": "role_context",
            })
        
        # Sort by priority
        actions.sort(key=lambda a: -a.get("priority", 0))
        
        return actions[:5]  # Top 5 recommendations

    def _compute_context_fingerprint(
        self,
        context: AdaptiveContext,
        profile: CompanyExperienceProfile,
    ) -> str:
        """Compute a fingerprint for the adaptive context for caching."""
        import hashlib
        parts = [
            context.organization_id,
            context.user_id,
            context.user_role.value,
            profile.value,
            context.geographic_context.value,
            context.device_type,
            str(sorted(context.user_permissions)),
        ]
        return hashlib.md5("|".join(parts).encode()).hexdigest()[:16]

    async def get_module_recommendations(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
        limit: int = 5,
    ) -> List[AdaptiveModule]:
        """Get personalized module recommendations for the user."""
        config = await company_experience_service.get_experience_config(db, context.organization_id)
        profile = config.experience_profile if config else CompanyExperienceProfile.STARTUP
        
        recommendations = []
        for module in MODULE_REGISTRY.values():
            if await self._is_module_visible(db, context, profile, module):
                # Skip already visible modules
                if module.key in context.user_permissions:
                    continue
                
                # Calculate relevance score
                role_score = module.role_affinity.get(context.user_role, 0.5)
                priority_score = module.priority / 100.0
                relevance = (role_score * 0.7) + (priority_score * 0.3)
                
                recommendations.append((module, relevance))
        
        # Sort by relevance
        recommendations.sort(key=lambda x: -x[1])
        
        return [m for m, _ in recommendations[:limit]]

    async def record_interaction(
        self,
        db: AsyncSession,
        context: AdaptiveContext,
        module_key: str,
        action: str,
    ) -> None:
        """Record user interaction for adaptive learning."""
        # In production, this would feed into a learning system
        # For now, log for analytics
        logger.info(f"Interaction: user={context.user_id} module={module_key} action={action}")

    async def get_profile_transition_preview(
        self,
        db: AsyncSession,
        organization_id: str,
        target_profile: CompanyExperienceProfile,
    ) -> Dict[str, Any]:
        """Preview what would change if transitioning to target profile."""
        current_config = await company_experience_service.get_experience_config(db, organization_id)
        current_profile = current_config.experience_profile if current_config else CompanyExperienceProfile.STARTUP
        
        current_caps = get_profile_capabilities(current_profile)
        target_caps = get_profile_capabilities(target_profile)
        
        return {
            "current_profile": current_profile.value,
            "target_profile": target_profile.value,
            "modules_added": list(set(target_caps.get("modules_enabled_by_default", [])) - 
                                set(current_caps.get("modules_enabled_by_default", []))),
            "modules_removed": list(set(current_caps.get("modules_enabled_by_default", [])) - 
                                  set(target_caps.get("modules_enabled_by_default", []))),
            "navigation_groups_added": list(set(target_caps.get("navigation_groups", [])) - 
                                          set(current_caps.get("navigation_groups", []))),
            "navigation_groups_removed": list(set(current_caps.get("navigation_groups", [])) - 
                                            set(target_caps.get("navigation_groups", []))),
            "governance_level_change": {
                "from": current_caps.get("governance_level"),
                "to": target_caps.get("governance_level"),
            },
            "approval_levels_change": {
                "from": current_caps.get("approval_levels"),
                "to": target_caps.get("approval_levels"),
            },
            "new_features": target_caps.get("features", []),
        }


adaptive_experience_engine = AdaptiveExperienceEngine()