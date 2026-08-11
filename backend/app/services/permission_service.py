"""Permission catalog and role seeding.

Permission codes follow `<resource>:<action>`. The catalog below is the
source of truth; new resources are appended as later phases land.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, RolePermission, UserRole

PERMISSIONS: list[tuple[str, str, str, Optional[str]]] = [
    # (code, name, resource, description)
    ("organization:read", "View Organization", "organization", "View organization profile and settings"),
    ("organization:update", "Update Organization", "organization", "Update organization profile and branding"),
    ("organization:settings", "Manage Organization Settings", "organization", "Manage organization security and retention settings"),
    ("organization:delete", "Delete Organization", "organization", "Delete the organization (owner only)"),
    ("dashboard:read", "View Dashboard", "dashboard", "View the home dashboard"),
    ("users:read", "View Users", "users", "View the employee directory"),
    ("users:invite", "Invite Users", "users", "Invite new employees"),
    ("users:manage", "Manage Users", "users", "Update users and change their status"),
    ("users:profile", "Edit Own Profile", "users", "Edit your own profile"),
    ("roles:read", "View Roles", "roles", "View roles and permissions"),
    ("roles:manage", "Manage Roles", "roles", "Create, update and delete roles"),
    ("permissions:read", "View Permissions", "permissions", "View the permission catalog"),
    ("notifications:read", "Read Notifications", "notifications", "Read notifications"),
    ("notifications:manage", "Manage Notifications", "notifications", "Broadcast organization notifications"),
    ("audit:read", "View Audit Log", "audit", "View the organization audit log"),
    ("audit:export", "Export Audit Log", "audit", "Export audit log entries"),
    ("workspace:read", "View Own Workspace", "workspace", "View the personal workspace"),
    ("workspace:manage", "Manage Own Workspace", "workspace", "Create and manage workspace items"),
    ("invitations:read", "View Invitations", "invitations", "View pending invitations"),
    ("invitations:manage", "Manage Invitations", "invitations", "Revoke and resend invitations"),
    ("sessions:read", "View Sessions", "sessions", "View active sessions"),
    ("sessions:manage", "Manage Sessions", "sessions", "Revoke sessions"),
    ("events:read", "View Events", "events", "View the organization event stream"),
    ("search:global", "Global Search", "search", "Search across the organization"),
    ("ai:use", "Use AI Companion", "ai", "Use the AI Companion foundation"),
    # Phase 2 — People & Organization
    ("employees:read", "View Employees", "employees", "View the employee directory and profiles"),
    ("employees:profile", "Edit Own Employee Profile", "employees", "Edit your own employee profile details"),
    ("employees:manage", "Manage Employees", "employees", "Create, update, transfer and archive employees"),
    ("employees:hire", "Hire Employees", "employees", "Create new employee records"),
    ("department:read", "View Departments", "department", "View departments and their members"),
    ("department:manage", "Manage Departments", "department", "Create, update and delete departments"),
    ("team:read", "View Teams", "team", "View teams and their members"),
    ("team:manage", "Manage Teams", "team", "Create, update and delete teams"),
    ("orgchart:read", "View Organization Chart", "orgchart", "View the organization chart and graph"),
    ("expertise:read", "View Expertise", "expertise", "View expertise scores, experts and successors"),
    ("presence:read", "View Presence", "presence", "View presence and availability"),
    ("favorites:manage", "Manage Favorites", "favorites", "Bookmark employees and teams"),
    ("intelligence:read", "View Background Intelligence", "intelligence", "View the background intelligence center, insights, patterns and briefs"),
    # Phase 3 — Work Execution Engine
    ("projects:read", "View Projects", "projects", "View projects, roadmaps, epics, milestones and sprints"),
    ("projects:manage", "Manage Projects", "projects", "Create, update and delete projects and their structure"),
    ("tasks:read", "View Tasks", "tasks", "View tasks and dependencies"),
    ("tasks:manage", "Manage Tasks", "tasks", "Create, update, transition and delete tasks"),
    ("calendar:read", "View Calendar", "calendar", "View calendar events"),
    ("calendar:manage", "Manage Calendar", "calendar", "Create, update and delete calendar events"),
    ("meetings:read", "View Meetings", "meetings", "View meetings and their details"),
    ("meetings:manage", "Manage Meetings", "meetings", "Schedule, update and complete meetings"),
    ("goals:read", "View Goals", "goals", "View goals and key results"),
    ("goals:manage", "Manage Goals", "goals", "Create, update and complete goals"),
    ("approvals:read", "View Approvals", "approvals", "View approval requests"),
    ("approvals:manage", "Manage Approvals", "approvals", "Create, approve and reject approval requests"),
    ("risks:read", "View Risks", "risks", "View project risks"),
    ("risks:manage", "Manage Risks", "risks", "Create, update and close risks"),
    ("workload:read", "View Workload", "workload", "View workload, capacity and utilization"),
    ("analytics:read", "View Work Analytics", "analytics", "View work intelligence and dashboards"),
    # Phase 4 — Knowledge Operating System
    ("knowledge:read", "View Knowledge", "knowledge", "View documents, wiki, policies, SOPs, templates and decisions"),
    ("knowledge:manage", "Manage Knowledge", "knowledge", "Create, edit, publish and delete knowledge entities"),
    ("knowledge:approve", "Approve Knowledge", "knowledge", "Approve or reject knowledge workflows (policies, documents)"),
    # Phase 5 — Communication & Community
    ("communication:read", "Use Communication", "communication", "View and participate in communities, posts, forums, polls, events, recognition, innovation and messaging"),
    ("communication:write", "Send Messages", "communication", "Send, edit, delete and react to conversation messages"),
    ("communication:manage", "Manage Communication", "communication", "Create and moderate communities, announcements, events and idea reviews"),
    # Phase 8 — Executive Intelligence
    ("executive:view", "View Executive Intelligence", "executive", "View the executive dashboard, digital twin, health, risks, predictions and reports"),
    ("executive:manage", "Manage Executive Intelligence", "executive", "Run simulations, generate executive reports and manage strategic goals"),
    # Phase 9 — Background Intelligence & Autonomous Organization
    ("intelligence:manage", "Manage Background Intelligence", "intelligence", "Run background workers on demand and manage insights, signals and feeds"),
    # Phase 10 — Learning & Growth Operating System
    ("learning:read", "View Learning", "learning", "View the learning center: profile, courses, paths, skills, assessments, mentors, certifications, career and onboarding"),
    ("learning:manage", "Manage Learning", "learning", "Create and manage courses, paths, assessments, certifications, academies, career paths and onboarding plans"),
    # Phase 11 — HR & Workforce Operations
    ("hr:read", "View HR", "hr", "View the HR hub: attendance, leave, performance, recruitment, assets, offboarding, compliance, workforce and wellbeing"),
    ("hr:manage", "Manage HR", "hr", "Create and manage shifts, holidays, leave types, jobs, candidates, offers, reviews, assets, offboarding, compliance and workforce plans"),
    ("payroll:read", "View Payroll", "payroll", "View payroll providers and run references"),
    ("payroll:manage", "Manage Payroll", "payroll", "Configure payroll providers and record payroll run references"),
    # Phase 12 — Customers, CRM & External Relationships
    ("crm:read", "View Customers", "crm", "View customers, leads, opportunities, contacts, contracts, support tickets, partners, vendors and customer analytics"),
    ("crm:manage", "Manage Customers", "crm", "Create and manage customers, leads, opportunities, contacts, contracts, support tickets, partners, vendors and portal users"),
    # Phase 13 — Finance & Business Operations
    ("finance:read", "View Finance", "finance", "View budgets, expenses, procurement, vendors, vendor contracts, invoices, payments, forecasts, financial analytics and risk"),
    ("finance:manage", "Manage Finance", "finance", "Create and manage budgets, expenses, purchase requests and orders, vendors, contracts, invoices, payments, integrations, forecasts and risk scans"),
    # Phase 14 — Workflow Automation & Business Process OS
    ("automation:read", "View Automation", "automation", "View workflows, executions, approvals, rules, schedules, templates, integrations and workflow analytics"),
    ("automation:manage", "Manage Automation", "automation", "Create and manage workflows, executions, approvals, business rules, schedules, templates, integrations and AI workflow generation"),
    # Phase 15 — Enterprise Platform, Extensibility & Global Administration
    ("enterprise:read", "View Enterprise Platform", "enterprise", "View the enterprise console: identity, plugins, marketplace, gateway, integrations, monitoring and governed AI"),
    ("enterprise:manage", "Manage Enterprise Platform", "enterprise", "Configure the enterprise console, AI consent and global administration"),
    ("identity:manage", "Manage Enterprise Identity", "enterprise", "Configure SSO providers, SCIM provisioning, MFA, passkeys, devices and authentication policies"),
    ("plugins:manage", "Manage Plugins", "enterprise", "Install, enable, disable, update and remove plugins and marketplace installs"),
    ("marketplace:manage", "Manage Marketplace", "enterprise", "Publish and moderate marketplace items"),
    ("api_keys:manage", "Manage API Keys", "enterprise", "Create, rotate and revoke API gateway keys and rate limits"),
    ("integrations:manage", "Manage Integrations", "enterprise", "Create, test, sync and remove integration connections"),
    ("monitoring:read", "View Monitoring", "enterprise", "View health, metrics and alerts"),
    ("observability:read", "View Observability", "enterprise", "View structured logs and traces"),
    ("security:manage", "Manage Security Center", "enterprise", "View and resolve security events, enforce policies and IP restrictions"),
    ("compliance:manage", "Manage Compliance", "enterprise", "Manage compliance controls, frameworks and readiness reporting"),
    ("licenses:manage", "Manage Licensing", "enterprise", "View and change license plans, seats and entitlements"),
    ("feature_flags:manage", "Manage Feature Flags", "enterprise", "Create, target and toggle enterprise feature flags"),
    # Phase 16 — Global Scale, Cloud Infrastructure & Enterprise Reliability
    ("infrastructure:read", "View Infrastructure", "infrastructure", "View cloud regions, deployment history, cluster topology, backups, DR runs, autoscaling, observability and reliability reports"),
    ("infrastructure:manage", "Manage Infrastructure", "infrastructure", "Manage regions, deployments, clusters, backups, disaster recovery, autoscaling and chaos engineering"),
    # Phase 17 — Industry Solutions & Vertical Intelligence Platform
    ("industry:read", "View Industry Packs", "industry", "View the industry catalog, marketplace, installed packs, modules, templates, workflows, compliance, AI profiles and analytics"),
    ("industry:manage", "Manage Industry Packs", "industry", "Install, select, enable, disable and uninstall industry packs, apply templates, run compliance checks, configure AI profiles and record KPI analytics"),
    # Phase 18 — Autonomous Enterprise Intelligence, Developer Ecosystem & AI Agent Ecosystem
    ("digital_twin:read", "View Digital Twin", "digital_twin", "View the organizational digital twin, health, predictions, simulations, forecasts, recommendations, optimization, decisions, executive brief and twin AI"),
    ("digital_twin:manage", "Manage Digital Twin", "digital_twin", "Refresh the twin, generate predictions, forecasts, recommendations and optimizations, run simulations, manage decisions and apply optimizations"),
    ("developers:read", "View Developer Portal", "developers", "View the developer portal, applications, apps, plugins, marketplace listings, webhooks, usage and analytics"),
    ("developers:manage", "Manage Developer Portal", "developers", "Create developer applications, publish apps and plugins, manage API keys, webhook endpoints and subscriptions"),
    ("webhooks:manage", "Manage Webhooks", "developers", "Create, update, delete and retry webhook endpoints and deliveries"),
    ("agents:read", "View AI Agents", "developers", "View the AI agent ecosystem: agents, extensions, marketplace installs and agent analytics"),
    ("agents:manage", "Manage AI Agents", "developers", "Create, publish and install AI agents and extensions"),
    ("marketplace:read", "View Marketplace", "developers", "Browse marketplace listings, installs, ratings and reviews"),
    ("marketplace:install", "Install Extensions", "developers", "Install, disable and uninstall marketplace extensions and AI agents"),
    ("theme:manage", "Manage Themes", "developers", "Create, apply and remove organization branding themes"),
    ("memory:read", "View Company Memory", "memory", "View permanent organizational memory, recall and search memories"),
    ("memory:manage", "Manage Company Memory", "memory", "Record, pin and delete organizational memories"),
    ("timeline:read", "View Organization Timeline", "timeline", "Browse the organization-wide company history timeline"),
    ("timeline:manage", "Record Timeline Entries", "timeline", "Add entries to the organization timeline"),
    ("context:read", "View Universal Context", "context", "View universal context bundles for any entity"),
    ("context:manage", "Manage Universal Context", "context", "Rebuild and attach context bundles"),
    # Phase 19 — Autonomous Enterprise & Intelligence Network
    ("autonomy:read", "View Autonomous Enterprise", "autonomy", "View organizational state, metrics, insights, plans, briefings and decision cases"),
    ("autonomy:manage", "Manage Autonomous Enterprise", "autonomy", "Trigger observation, generate plans and briefings, and decide decision cases"),
    ("predictions:read", "View Predictions", "predictions", "View predictive intelligence, model health and prediction history"),
    ("predictions:manage", "Manage Predictions", "predictions", "Generate, update and validate predictions"),
    ("innovation:read", "View Innovation", "innovation", "View tracked innovations, ideas and recommendations"),
    ("innovation:manage", "Manage Innovation", "innovation", "Run innovation scans and manage the innovation funnel"),
    # Phase 20 — Universal Organizational Intelligence Network (Company Brain)
    ("brain:read", "Use Company Brain", "brain", "View the unified company overview, ask the universal AI, use universal search, graph, health, memory, timeline, context and events"),
    ("brain:manage", "Manage Company Brain", "brain", "Trigger evolution cycles, rebuild the universal graph, generate executive intelligence and briefings, refresh company health"),
    # Slice 4C — Governance, RBAC & Enterprise Control Foundation
    ("governance:read", "View Governance", "governance", "View scopes, scoped assignments, delegations, approval policies and effective permissions"),
    ("governance:manage", "Manage Governance", "governance", "Create scopes, assign scoped roles, delegate and revoke authority, manage approval policies"),
]

# Default roles created for every new organization.
_PEOPLE_ALL = [
    "employees:read", "employees:profile", "employees:manage", "employees:hire",
    "department:read", "department:manage", "team:read", "team:manage",
    "orgchart:read", "expertise:read", "presence:read", "favorites:manage", "intelligence:read",
]

# Phase 3 — Work Execution Engine
_WORK_ALL = [
    "projects:read", "projects:manage", "tasks:read", "tasks:manage",
    "calendar:read", "calendar:manage", "meetings:read", "meetings:manage",
    "goals:read", "goals:manage", "workload:read", "analytics:read",
]
_WORK_READ = [
    "projects:read", "tasks:read", "calendar:read", "meetings:read", "goals:read", "workload:read",
]
_APPROVAL_ALL = ["approvals:read", "approvals:manage", "risks:read", "risks:manage"]

# Phase 4 — Knowledge Operating System
_KNOWLEDGE_ALL = ["knowledge:read", "knowledge:manage", "knowledge:approve"]
_KNOWLEDGE_READ = ["knowledge:read"]
_KNOWLEDGE_WRITE = ["knowledge:read", "knowledge:manage"]

# Phase 5 — Communication & Community
_COMMUNICATION_ALL = ["communication:read", "communication:write", "communication:manage"]
_COMMUNICATION_READ = ["communication:read"]

# Phase 10 — Learning & Growth Operating System
_LEARNING_ALL = ["learning:read", "learning:manage"]
_LEARNING_READ = ["learning:read"]

# Phase 11 — HR & Workforce Operations
_HR_ALL = ["hr:read", "hr:manage"]
_HR_READ = ["hr:read"]
_PAYROLL_READ = ["payroll:read"]
_PAYROLL_MANAGE = ["payroll:read", "payroll:manage"]

# Phase 12 — Customers, CRM & External Relationships
_CRM_ALL = ["crm:read", "crm:manage"]
_CRM_READ = ["crm:read"]

# Phase 13 — Finance & Business Operations
_FINANCE_ALL = ["finance:read", "finance:manage"]
_FINANCE_READ = ["finance:read"]

# Phase 14 — Workflow Automation & Business Process OS
_AUTOMATION_ALL = ["automation:read", "automation:manage"]
_AUTOMATION_READ = ["automation:read"]

# Phase 15 — Enterprise Platform, Extensibility & Global Administration
_ENTERPRISE_ALL = [
    "enterprise:read", "enterprise:manage",
    "identity:manage", "plugins:manage", "marketplace:manage",
    "api_keys:manage", "integrations:manage", "monitoring:read",
    "observability:read", "security:manage", "compliance:manage",
    "licenses:manage", "feature_flags:manage",
]
_ENTERPRISE_READ = ["enterprise:read", "monitoring:read", "observability:read"]

# Phase 16 — Global Scale, Cloud Infrastructure & Enterprise Reliability
_INFRASTRUCTURE_ALL = ["infrastructure:read", "infrastructure:manage"]
_INFRASTRUCTURE_READ = ["infrastructure:read"]

# Phase 17 — Industry Solutions & Vertical Intelligence Platform
_INDUSTRY_ALL = ["industry:read", "industry:manage"]
_INDUSTRY_READ = ["industry:read"]

# Phase 18 — Autonomous Enterprise Intelligence & Developer Ecosystem
_DIGITAL_TWIN_ALL = ["digital_twin:read", "digital_twin:manage"]
_DIGITAL_TWIN_READ = ["digital_twin:read"]
_DEVELOPERS_ALL = [
    "developers:read", "developers:manage", "webhooks:manage", "agents:read", "agents:manage",
    "marketplace:read", "marketplace:install", "theme:manage",
]
_DEVELOPERS_READ = ["developers:read", "agents:read", "marketplace:read"]

# Phase 19 — Company Memory & Universal Context
_MEMORY_ALL = ["memory:read", "memory:manage"]
_MEMORY_READ = ["memory:read"]
_TIMELINE_ALL = ["timeline:read", "timeline:manage"]
_TIMELINE_READ = ["timeline:read"]
_CONTEXT_ALL = ["context:read", "context:manage"]
_CONTEXT_READ = ["context:read"]

# Phase 19 — Autonomous Enterprise & Intelligence Network
_AUTONOMY_ALL = ["autonomy:read", "autonomy:manage"]
_AUTONOMY_READ = ["autonomy:read"]
_PREDICTIONS_ALL = ["predictions:read", "predictions:manage"]
_PREDICTIONS_READ = ["predictions:read"]
_INNOVATION_ALL = ["innovation:read", "innovation:manage"]
_INNOVATION_READ = ["innovation:read"]

# Phase 20 — Universal Organizational Intelligence Network
_BRAIN_ALL = ["brain:read", "brain:manage"]
_BRAIN_READ = ["brain:read"]

# Slice 4C — Governance, RBAC & Enterprise Control Foundation
_GOVERNANCE_ALL = ["governance:read", "governance:manage"]
_GOVERNANCE_READ = ["governance:read"]

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "ceo": [
        "organization:read", "organization:update", "organization:settings", "organization:delete",
        "dashboard:read", "users:read", "users:invite", "users:manage", "users:profile",
        "roles:read", "roles:manage", "permissions:read",
        "notifications:read", "notifications:manage", "audit:read", "audit:export",
        "workspace:read", "workspace:manage", "invitations:read", "invitations:manage",
        "sessions:read", "sessions:manage", "events:read", "search:global", "ai:use",
        *_PEOPLE_ALL,
        *_WORK_ALL,
        *_APPROVAL_ALL,
        *_KNOWLEDGE_ALL,
        *_COMMUNICATION_ALL,
        "executive:view", "executive:manage",
        "intelligence:read", "intelligence:manage",
        *_LEARNING_ALL,
        *_HR_ALL,
        *_PAYROLL_MANAGE,
        *_CRM_ALL,
        *_FINANCE_ALL,
        *_AUTOMATION_ALL,
        *_ENTERPRISE_ALL,
        *_INFRASTRUCTURE_ALL,
        *_INDUSTRY_ALL,
        *_DIGITAL_TWIN_ALL,
        *_DEVELOPERS_ALL,
        *_MEMORY_ALL,
        *_TIMELINE_ALL,
        *_CONTEXT_ALL,
        *_AUTONOMY_ALL,
        *_PREDICTIONS_ALL,
        *_INNOVATION_ALL,
        *_BRAIN_ALL,
        *_GOVERNANCE_ALL,
    ],
    "admin": [
        "organization:read", "organization:update", "organization:settings",
        "dashboard:read", "users:read", "users:invite", "users:manage", "users:profile",
        "roles:read", "roles:manage", "permissions:read",
        "notifications:read", "notifications:manage", "audit:read", "audit:export",
        "workspace:read", "workspace:manage", "invitations:read", "invitations:manage",
        "sessions:read", "sessions:manage", "events:read", "search:global", "ai:use",
        *_PEOPLE_ALL,
        *_WORK_ALL,
        *_APPROVAL_ALL,
        *_KNOWLEDGE_ALL,
        *_COMMUNICATION_ALL,
        "executive:view",
        "intelligence:read",
        *_LEARNING_ALL,
        *_HR_ALL,
        *_PAYROLL_MANAGE,
        *_CRM_ALL,
        *_FINANCE_ALL,
        *_AUTOMATION_ALL,
        *_ENTERPRISE_ALL,
        *_INDUSTRY_ALL,
        *_DIGITAL_TWIN_ALL,
        *_DEVELOPERS_ALL,
        *_MEMORY_ALL,
        *_TIMELINE_ALL,
        *_CONTEXT_ALL,
        *_AUTONOMY_ALL,
        *_PREDICTIONS_ALL,
        *_INNOVATION_ALL,
        *_BRAIN_ALL,
        *_GOVERNANCE_ALL,
    ],
    "hr": [
        "organization:read", "dashboard:read", "users:read", "users:invite", "users:manage",
        "users:profile", "roles:read", "notifications:read", "audit:read",
        "workspace:read", "workspace:manage", "invitations:read", "invitations:manage",
        "sessions:read", "sessions:manage", "search:global", "ai:use",
        "employees:read", "employees:profile", "employees:manage", "employees:hire",
        "department:read", "department:manage", "team:read", "team:manage",
        "orgchart:read", "expertise:read", "presence:read", "favorites:manage", "intelligence:read",
        *_WORK_READ,
        *_KNOWLEDGE_ALL,
        *_COMMUNICATION_READ,
        *_LEARNING_ALL,
        *_HR_ALL,
        *_PAYROLL_MANAGE,
        *_FINANCE_READ,
        *_AUTOMATION_READ,
        *_CRM_READ,
        *_INDUSTRY_READ,
        *_DIGITAL_TWIN_READ,
        *_MEMORY_READ,
        *_TIMELINE_READ,
        *_CONTEXT_READ,
        *_AUTONOMY_READ,
        *_PREDICTIONS_READ,
        *_INNOVATION_READ,
        *_BRAIN_READ,
        *_GOVERNANCE_READ,
    ],
    "manager": [
        "organization:read", "dashboard:read", "users:read", "users:profile",
        "roles:read", "notifications:read", "workspace:read", "workspace:manage",
        "search:global", "ai:use",
        "employees:read", "employees:profile",
        "department:read", "team:read", "orgchart:read", "expertise:read",
        "presence:read", "favorites:manage", "intelligence:read",
        *_LEARNING_ALL,
        *_HR_READ,
        "projects:read", "projects:manage", "tasks:read", "tasks:manage",
        "calendar:read", "calendar:manage", "meetings:read", "meetings:manage",
        "goals:read", "goals:manage", "approvals:read", "approvals:manage",
        "risks:read", "workload:read", "analytics:read",
        *_KNOWLEDGE_ALL,
        *_COMMUNICATION_ALL,
        *_CRM_ALL,
        *_FINANCE_ALL,
        *_AUTOMATION_ALL,
        *_ENTERPRISE_READ,
        *_INFRASTRUCTURE_READ,
        *_INDUSTRY_READ,
        *_DIGITAL_TWIN_READ,
        *_DEVELOPERS_READ,
        *_MEMORY_READ,
        *_TIMELINE_READ,
        *_CONTEXT_READ,
        *_AUTONOMY_READ,
        *_PREDICTIONS_READ,
        *_INNOVATION_READ,
        *_BRAIN_READ,
        *_GOVERNANCE_READ,
    ],
    "employee": [        "organization:read", "dashboard:read", "users:read", "users:profile",
        "notifications:read", "workspace:read", "workspace:manage",
        "sessions:read", "sessions:manage", "search:global", "ai:use",
        "employees:read", "employees:profile",
        "department:read", "team:read", "orgchart:read", "expertise:read",
        "presence:read", "favorites:manage",
        *_LEARNING_READ,
        *_HR_READ,
        *_WORK_READ,
        *_KNOWLEDGE_READ,
        *_COMMUNICATION_READ,
        *_CRM_READ,
        *_FINANCE_READ,
        *_AUTOMATION_READ,
        *_INDUSTRY_READ,
        *_DIGITAL_TWIN_READ,
        *_MEMORY_READ,
        *_TIMELINE_READ,
        *_CONTEXT_READ,
        *_AUTONOMY_READ,
        *_PREDICTIONS_READ,
        *_INNOVATION_READ,
        *_BRAIN_READ,
    ],
    "finance": [
        "organization:read", "dashboard:read", "users:read", "users:profile",
        "roles:read", "notifications:read", "audit:read",
        "workspace:read", "workspace:manage", "search:global", "ai:use",
        "employees:read", "department:read", "team:read", "orgchart:read",
        "expertise:read", "presence:read",
        "projects:read", "tasks:read", "calendar:read", "meetings:read", "goals:read",
        "approvals:read", "risks:read", "workload:read", "analytics:read",
        *_KNOWLEDGE_ALL,
        *_COMMUNICATION_ALL,
        *_HR_READ,
        *_PAYROLL_MANAGE,
        *_CRM_READ,
        *_FINANCE_ALL,
        *_AUTOMATION_READ,
        *_INDUSTRY_READ,
        *_AUTONOMY_READ,
        *_PREDICTIONS_READ,
        *_INNOVATION_READ,
        *_BRAIN_READ,
        *_GOVERNANCE_READ,
    ],
}

ROLE_LABELS: dict[str, str] = {
    "ceo": "CEO",
    "admin": "Administrator",
    "hr": "Human Resources",
    "manager": "Manager",
    "employee": "Employee",
    "finance": "Finance",
}

ROLE_ORDER = ["ceo", "admin", "manager", "hr", "finance", "employee"]


class PermissionService:
    async def sync_catalog(self, db: AsyncSession) -> None:
        """Insert any missing global permissions (idempotent)."""
        existing = set(
            (await db.execute(select(Permission.code))).scalars().all()
        )
        for code, name, resource, description in PERMISSIONS:
            if code not in existing:
                db.add(Permission(code=code, name=name, resource=resource, action=code.split(":")[1], description=description))
        await db.flush()

    async def sync_role_permissions(self, db: AsyncSession) -> None:
        """Add missing default permissions to existing system roles (idempotent).

        Called on startup so organizations created before a phase upgrade get the
        new permission set without re-seeding.
        """
        permissions = {p.code: p for p in await self.catalog(db)}
        roles = (await db.execute(select(Role).where(Role.is_system.is_(True)))).scalars().all()
        for role in roles:
            defaults = DEFAULT_ROLE_PERMISSIONS.get(role.code)
            if not defaults:
                continue
            existing = {
                row[0]
                for row in (
                    await db.execute(
                        select(Permission.code)
                        .join(RolePermission, RolePermission.permission_id == Permission.id)
                        .where(RolePermission.role_id == role.id)
                    )
                ).all()
            }
            for code in defaults:
                perm = permissions.get(code)
                if perm and code not in existing:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        await db.flush()

    async def catalog(self, db: AsyncSession) -> list[Permission]:
        result = await db.execute(select(Permission).order_by(Permission.resource, Permission.action))
        return list(result.scalars().all())

    async def get_codes(self, db: AsyncSession, permission_ids: list[str]) -> list[str]:
        if not permission_ids:
            return []
        result = await db.execute(select(Permission.code).where(Permission.id.in_(permission_ids)))
        return list(result.scalars().all())

    async def seed_org_roles(self, db: AsyncSession, organization_id: str) -> dict[str, Role]:
        """Create the default system roles for a fresh organization."""
        roles: dict[str, Role] = {}
        permissions = {p.code: p for p in await self.catalog(db)}
        for code in ROLE_ORDER:
            perms = DEFAULT_ROLE_PERMISSIONS[code]
            role = Role(
                organization_id=organization_id,
                name=ROLE_LABELS[code],
                code=code,
                description=f"System {ROLE_LABELS[code]} role",
                is_system=True,
                is_default=(code == "employee"),
            )
            db.add(role)
            await db.flush()
            for perm_code in perms:
                perm = permissions.get(perm_code)
                if perm:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            roles[code] = role
        await db.flush()
        return roles

    async def user_permission_codes(self, db: AsyncSession, user_id: str, organization_id: str) -> set[str]:
        """Effective permission codes for a user: organization-wide roles plus
        active organization-wide delegations.

        Organization-wide only — scoped (ABAC) authority is layered on top by
        the governance service when the caller resolves a scope. Queries are
        bounded by the user's own roles and grants, never by org size.
        """
        from sqlalchemy import or_

        rows = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.organization_id == organization_id,
                UserRole.scope_id.is_(None),
            )
        )
        codes = set(rows.scalars().all())
        from app.core.timeutils import utcnow
        from app.models.enterprise import AccessGrant

        grants = await db.execute(
            select(AccessGrant.permission_code).where(
                AccessGrant.organization_id == organization_id,
                AccessGrant.granted_to_user == user_id,
                AccessGrant.status == "active",
                AccessGrant.resource_type.is_(None),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > utcnow()),
                or_(AccessGrant.starts_at.is_(None), AccessGrant.starts_at <= utcnow()),
            )
        )
        codes.update(grants.scalars().all())
        return codes

    async def role_permission_codes(self, db: AsyncSession, role_id: str) -> set[str]:
        """Permission codes granted by a single role."""
        rows = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return set(rows.scalars().all())

    async def assign_role(self, db: AsyncSession, *, user_id: str, role_id: str, organization_id: str, replace_all: bool = True) -> None:
        if replace_all:
            existing = await db.execute(
                select(UserRole).where(
                    UserRole.user_id == user_id, UserRole.organization_id == organization_id
                )
            )
            for row in existing.scalars().all():
                await db.delete(row)
        role = await db.get(Role, role_id)
        if role and role.organization_id == organization_id:
            db.add(
                UserRole(
                    user_id=user_id,
                    role_id=role_id,
                    organization_id=organization_id,
                )
            )
        await db.flush()


permission_service = PermissionService()
