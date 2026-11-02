/**
 * RBAC permission constants — mirror the backend permission catalog.
 * The backend enforces everything; the frontend uses these to show/hide UI.
 */

export const PERMISSIONS = {
  ORGANIZATION_READ: "organization:read",
  ORGANIZATION_UPDATE: "organization:update",
  ORGANIZATION_SETTINGS: "organization:settings",
  DASHBOARD_READ: "dashboard:read",
  USERS_READ: "users:read",
  USERS_INVITE: "users:invite",
  USERS_MANAGE: "users:manage",
  ROLES_READ: "roles:read",
  ROLES_MANAGE: "roles:manage",
  PERMISSIONS_READ: "permissions:read",
  NOTIFICATIONS_READ: "notifications:read",
  AUDIT_READ: "audit:read",
  AUDIT_EXPORT: "audit:export",
  WORKSPACE_READ: "workspace:read",
  WORKSPACE_MANAGE: "workspace:manage",
  WORKSPACE_COMMAND: "workspace:command",
  INVITATIONS_READ: "invitations:read",
  INVITATIONS_MANAGE: "invitations:manage",
  SESSIONS_READ: "sessions:read",
  SESSIONS_MANAGE: "sessions:manage",
  EVENTS_READ: "events:read",
  SEARCH_GLOBAL: "search:global",
  AI_USE: "ai:use",
  EMPLOYEES_READ: "employees:read",
  EMPLOYEES_PROFILE: "employees:profile",
  EMPLOYEES_MANAGE: "employees:manage",
  EMPLOYEES_HIRE: "employees:hire",
  DEPARTMENT_READ: "department:read",
  DEPARTMENT_MANAGE: "department:manage",
  TEAM_READ: "team:read",
  TEAM_MANAGE: "team:manage",
  ORGCHART_READ: "orgchart:read",
  EXPERTISE_READ: "expertise:read",
  PRESENCE_READ: "presence:read",
  FAVORITES_MANAGE: "favorites:manage",
  INTELLIGENCE_READ: "intelligence:read",
  PROJECTS_READ: "projects:read",
  PROJECTS_MANAGE: "projects:manage",
  TASKS_READ: "tasks:read",
  TASKS_MANAGE: "tasks:manage",
  CALENDAR_READ: "calendar:read",
  CALENDAR_MANAGE: "calendar:manage",
  MEETINGS_READ: "meetings:read",
  MEETINGS_MANAGE: "meetings:manage",
  GOALS_READ: "goals:read",
  GOALS_MANAGE: "goals:manage",
  APPROVALS_READ: "approvals:read",
  APPROVALS_MANAGE: "approvals:manage",
  RISKS_READ: "risks:read",
  RISKS_MANAGE: "risks:manage",
  WORKLOAD_READ: "workload:read",
  ANALYTICS_READ: "analytics:read",
  EMBEDDED_ANALYTICS_VIEW: "embedded_analytics:view",
  EMBEDDED_ANALYTICS_MANAGE: "embedded_analytics:manage",
  KNOWLEDGE_READ: "knowledge:read",
  KNOWLEDGE_SEARCH: "knowledge:search",
  KNOWLEDGE_MANAGE: "knowledge:manage",
  KNOWLEDGE_APPROVE: "knowledge:approve",
  COMMUNICATION_READ: "communication:read",
  COMMUNICATION_MANAGE: "communication:manage",
  EXECUTIVE_VIEW: "executive:view",
  EXECUTIVE_MANAGE: "executive:manage",
  INTELLIGENCE_MANAGE: "intelligence:manage",
  LEARNING_READ: "learning:read",
  LEARNING_MANAGE: "learning:manage",
  HR_READ: "hr:read",
  HR_MANAGE: "hr:manage",
  PAYROLL_READ: "payroll:read",
  PAYROLL_MANAGE: "payroll:manage",
  CRM_READ: "crm:read",
  CRM_MANAGE: "crm:manage",
  FINANCE_READ: "finance:read",
  FINANCE_MANAGE: "finance:manage",
  ENTERPRISE_READ: "enterprise:read",
  ENTERPRISE_MANAGE: "enterprise:manage",
  IDENTITY_MANAGE: "identity:manage",
  PLUGINS_MANAGE: "plugins:manage",
  MARKETPLACE_MANAGE: "marketplace:manage",
  API_KEYS_MANAGE: "api_keys:manage",
  INTEGRATIONS_MANAGE: "integrations:manage",
  MONITORING_READ: "monitoring:read",
  OBSERVABILITY_READ: "observability:read",
  SECURITY_MANAGE: "security:manage",
  COMPLIANCE_MANAGE: "compliance:manage",
  LICENSES_MANAGE: "licenses:manage",
  FEATURE_FLAGS_MANAGE: "feature_flags:manage",
  INDUSTRY_READ: "industry:read",
  INDUSTRY_MANAGE: "industry:manage",
  DIGITAL_TWIN_READ: "digital_twin:read",
  DIGITAL_TWIN_MANAGE: "digital_twin:manage",
  DEVELOPERS_READ: "developers:read",
  DEVELOPERS_MANAGE: "developers:manage",
  WEBHOOKS_MANAGE: "webhooks:manage",
  AGENTS_READ: "agents:read",
  AGENTS_MANAGE: "agents:manage",
  MARKETPLACE_READ: "marketplace:read",
  MARKETPLACE_INSTALL: "marketplace:install",
  THEME_MANAGE: "theme:manage",
  GOVERNANCE_READ: "governance:read",
  GOVERNANCE_MANAGE: "governance:manage",
  BRAIN_READ: "brain:read",
  BRAIN_MANAGE: "brain:manage",
} as const;

export type PermissionCode = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

const WORK_READ: PermissionCode[] = [
  PERMISSIONS.PROJECTS_READ,
  PERMISSIONS.TASKS_READ,
  PERMISSIONS.CALENDAR_READ,
  PERMISSIONS.MEETINGS_READ,
  PERMISSIONS.GOALS_READ,
  PERMISSIONS.WORKLOAD_READ,
];

const WORK_MANAGE: PermissionCode[] = [
  PERMISSIONS.PROJECTS_READ,
  PERMISSIONS.PROJECTS_MANAGE,
  PERMISSIONS.TASKS_READ,
  PERMISSIONS.TASKS_MANAGE,
  PERMISSIONS.CALENDAR_READ,
  PERMISSIONS.CALENDAR_MANAGE,
  PERMISSIONS.MEETINGS_READ,
  PERMISSIONS.MEETINGS_MANAGE,
  PERMISSIONS.GOALS_READ,
  PERMISSIONS.GOALS_MANAGE,
  PERMISSIONS.WORKLOAD_READ,
  PERMISSIONS.ANALYTICS_READ,
];

const KNOWLEDGE_READ: PermissionCode[] = [
  PERMISSIONS.KNOWLEDGE_READ,
  PERMISSIONS.KNOWLEDGE_SEARCH,
];

const KNOWLEDGE_ALL: PermissionCode[] = [
  PERMISSIONS.KNOWLEDGE_READ,
  PERMISSIONS.KNOWLEDGE_SEARCH,
  PERMISSIONS.KNOWLEDGE_MANAGE,
  PERMISSIONS.KNOWLEDGE_APPROVE,
];

const COMMUNICATION_READ: PermissionCode[] = [PERMISSIONS.COMMUNICATION_READ];

const COMMUNICATION_ALL: PermissionCode[] = [
  PERMISSIONS.COMMUNICATION_READ,
  PERMISSIONS.COMMUNICATION_MANAGE,
];

const LEARNING_READ: PermissionCode[] = [PERMISSIONS.LEARNING_READ];

const LEARNING_ALL: PermissionCode[] = [
  PERMISSIONS.LEARNING_READ,
  PERMISSIONS.LEARNING_MANAGE,
];

const HR_READ: PermissionCode[] = [PERMISSIONS.HR_READ];

const HR_ALL: PermissionCode[] = [PERMISSIONS.HR_READ, PERMISSIONS.HR_MANAGE];

const PAYROLL_READ: PermissionCode[] = [PERMISSIONS.PAYROLL_READ];

const PAYROLL_ALL: PermissionCode[] = [
  PERMISSIONS.PAYROLL_READ,
  PERMISSIONS.PAYROLL_MANAGE,
];

const CRM_READ: PermissionCode[] = [PERMISSIONS.CRM_READ];

const CRM_ALL: PermissionCode[] = [
  PERMISSIONS.CRM_READ,
  PERMISSIONS.CRM_MANAGE,
];

const FINANCE_READ: PermissionCode[] = [PERMISSIONS.FINANCE_READ];

const FINANCE_ALL: PermissionCode[] = [
  PERMISSIONS.FINANCE_READ,
  PERMISSIONS.FINANCE_MANAGE,
];

const ENTERPRISE_READ: PermissionCode[] = [PERMISSIONS.ENTERPRISE_READ];

const ENTERPRISE_ALL: PermissionCode[] = [
  PERMISSIONS.ENTERPRISE_READ,
  PERMISSIONS.ENTERPRISE_MANAGE,
  PERMISSIONS.IDENTITY_MANAGE,
  PERMISSIONS.PLUGINS_MANAGE,
  PERMISSIONS.MARKETPLACE_MANAGE,
  PERMISSIONS.API_KEYS_MANAGE,
  PERMISSIONS.INTEGRATIONS_MANAGE,
  PERMISSIONS.MONITORING_READ,
  PERMISSIONS.OBSERVABILITY_READ,
  PERMISSIONS.SECURITY_MANAGE,
  PERMISSIONS.COMPLIANCE_MANAGE,
  PERMISSIONS.LICENSES_MANAGE,
  PERMISSIONS.FEATURE_FLAGS_MANAGE,
];

const INDUSTRY_READ: PermissionCode[] = [PERMISSIONS.INDUSTRY_READ];

const INDUSTRY_ALL: PermissionCode[] = [
  PERMISSIONS.INDUSTRY_READ,
  PERMISSIONS.INDUSTRY_MANAGE,
];

const DIGITAL_TWIN_READ: PermissionCode[] = [PERMISSIONS.DIGITAL_TWIN_READ];

const DIGITAL_TWIN_ALL: PermissionCode[] = [
  PERMISSIONS.DIGITAL_TWIN_READ,
  PERMISSIONS.DIGITAL_TWIN_MANAGE,
];

const DEVELOPERS_READ: PermissionCode[] = [
  PERMISSIONS.DEVELOPERS_READ,
  PERMISSIONS.AGENTS_READ,
  PERMISSIONS.MARKETPLACE_READ,
];

const DEVELOPERS_ALL: PermissionCode[] = [
  PERMISSIONS.DEVELOPERS_READ,
  PERMISSIONS.DEVELOPERS_MANAGE,
  PERMISSIONS.WEBHOOKS_MANAGE,
  PERMISSIONS.AGENTS_READ,
  PERMISSIONS.AGENTS_MANAGE,
  PERMISSIONS.MARKETPLACE_READ,
  PERMISSIONS.MARKETPLACE_INSTALL,
  PERMISSIONS.THEME_MANAGE,
];

const GOVERNANCE_READ: PermissionCode[] = [PERMISSIONS.GOVERNANCE_READ];

const GOVERNANCE_ALL: PermissionCode[] = [
  PERMISSIONS.GOVERNANCE_READ,
  PERMISSIONS.GOVERNANCE_MANAGE,
];

const ROLE_PERMISSIONS: Record<string, PermissionCode[]> = {
  ceo: Object.values(PERMISSIONS),
  admin: Object.values(PERMISSIONS),
  hr: [
    PERMISSIONS.ORGANIZATION_READ,
    PERMISSIONS.DASHBOARD_READ,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.USERS_INVITE,
    PERMISSIONS.USERS_MANAGE,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.NOTIFICATIONS_READ,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.WORKSPACE_READ,
    PERMISSIONS.WORKSPACE_MANAGE,
    PERMISSIONS.INVITATIONS_READ,
    PERMISSIONS.INVITATIONS_MANAGE,
    PERMISSIONS.SESSIONS_READ,
    PERMISSIONS.SEARCH_GLOBAL,
    PERMISSIONS.AI_USE,
    PERMISSIONS.EMPLOYEES_READ,
    PERMISSIONS.EMPLOYEES_PROFILE,
    PERMISSIONS.EMPLOYEES_MANAGE,
    PERMISSIONS.EMPLOYEES_HIRE,
    PERMISSIONS.DEPARTMENT_READ,
    PERMISSIONS.DEPARTMENT_MANAGE,
    PERMISSIONS.TEAM_READ,
    PERMISSIONS.TEAM_MANAGE,
    PERMISSIONS.ORGCHART_READ,
    PERMISSIONS.EXPERTISE_READ,
    PERMISSIONS.PRESENCE_READ,
    PERMISSIONS.FAVORITES_MANAGE,
    PERMISSIONS.INTELLIGENCE_READ,
    ...WORK_READ,
    ...KNOWLEDGE_ALL,
    ...COMMUNICATION_READ,
    ...LEARNING_READ,
    ...HR_ALL,
    ...PAYROLL_ALL,
    ...FINANCE_READ,
    ...ENTERPRISE_ALL,
    ...INDUSTRY_ALL,
    ...DIGITAL_TWIN_ALL,
    ...DEVELOPERS_ALL,
    ...GOVERNANCE_READ,
  ],
  manager: [
    PERMISSIONS.ORGANIZATION_READ,
    PERMISSIONS.DASHBOARD_READ,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.NOTIFICATIONS_READ,
    PERMISSIONS.WORKSPACE_READ,
    PERMISSIONS.WORKSPACE_MANAGE,
    PERMISSIONS.SEARCH_GLOBAL,
    PERMISSIONS.AI_USE,
    PERMISSIONS.EMPLOYEES_READ,
    PERMISSIONS.EMPLOYEES_PROFILE,
    PERMISSIONS.DEPARTMENT_READ,
    PERMISSIONS.TEAM_READ,
    PERMISSIONS.ORGCHART_READ,
    PERMISSIONS.EXPERTISE_READ,
    PERMISSIONS.PRESENCE_READ,
    PERMISSIONS.FAVORITES_MANAGE,
    PERMISSIONS.INTELLIGENCE_READ,
    ...WORK_MANAGE,
    PERMISSIONS.APPROVALS_READ,
    PERMISSIONS.APPROVALS_MANAGE,
    PERMISSIONS.RISKS_READ,
    ...KNOWLEDGE_ALL,
    ...COMMUNICATION_ALL,
    ...LEARNING_ALL,
    ...HR_READ,
    ...CRM_ALL,
    ...FINANCE_ALL,
    ...ENTERPRISE_READ,
    ...INDUSTRY_READ,
    ...DIGITAL_TWIN_READ,
    ...DEVELOPERS_READ,
    ...GOVERNANCE_READ,
  ],
  employee: [
    PERMISSIONS.ORGANIZATION_READ,
    PERMISSIONS.DASHBOARD_READ,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.NOTIFICATIONS_READ,
    PERMISSIONS.WORKSPACE_READ,
    PERMISSIONS.WORKSPACE_MANAGE,
    PERMISSIONS.SESSIONS_READ,
    PERMISSIONS.SESSIONS_MANAGE,
    PERMISSIONS.SEARCH_GLOBAL,
    PERMISSIONS.AI_USE,
    PERMISSIONS.EMPLOYEES_READ,
    PERMISSIONS.EMPLOYEES_PROFILE,
    PERMISSIONS.DEPARTMENT_READ,
    PERMISSIONS.TEAM_READ,
    PERMISSIONS.ORGCHART_READ,
    PERMISSIONS.EXPERTISE_READ,
    PERMISSIONS.PRESENCE_READ,
    PERMISSIONS.FAVORITES_MANAGE,
    ...WORK_READ,
    ...KNOWLEDGE_READ,
    ...COMMUNICATION_READ,
    ...LEARNING_READ,
    ...HR_READ,
    ...CRM_READ,
    ...FINANCE_READ,
    ...ENTERPRISE_READ,
    ...INDUSTRY_READ,
    ...DIGITAL_TWIN_READ,
  ],
  finance: [
    PERMISSIONS.ORGANIZATION_READ,
    PERMISSIONS.DASHBOARD_READ,
    PERMISSIONS.USERS_READ,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.NOTIFICATIONS_READ,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.WORKSPACE_READ,
    PERMISSIONS.WORKSPACE_MANAGE,
    PERMISSIONS.SEARCH_GLOBAL,
    PERMISSIONS.AI_USE,
    PERMISSIONS.EMPLOYEES_READ,
    PERMISSIONS.DEPARTMENT_READ,
    PERMISSIONS.TEAM_READ,
    PERMISSIONS.ORGCHART_READ,
    PERMISSIONS.EXPERTISE_READ,
    PERMISSIONS.PRESENCE_READ,
    PERMISSIONS.PROJECTS_READ,
    PERMISSIONS.TASKS_READ,
    PERMISSIONS.CALENDAR_READ,
    PERMISSIONS.MEETINGS_READ,
    PERMISSIONS.GOALS_READ,
    PERMISSIONS.APPROVALS_READ,
    PERMISSIONS.RISKS_READ,
    PERMISSIONS.WORKLOAD_READ,
    PERMISSIONS.ANALYTICS_READ,
    ...KNOWLEDGE_ALL,
    ...COMMUNICATION_ALL,
    ...HR_READ,
    ...PAYROLL_READ,
    ...FINANCE_ALL,
    ...GOVERNANCE_READ,
  ],
};

export function roleCan(
  role: string | null | undefined,
  permission: PermissionCode,
): boolean {
  if (!role) return false;
  return (ROLE_PERMISSIONS[role] ?? []).includes(permission);
}

/** Resolve permission ids by code for the roles editor (client-side catalog mirror). */
export const PERMISSION_GROUPS: {
  resource: string;
  items: { id: string; code: string; name: string }[];
}[] = [
  {
    resource: "organization",
    items: [
      { id: "org-read", code: "organization:read", name: "View organization" },
      {
        id: "org-update",
        code: "organization:update",
        name: "Update organization",
      },
      {
        id: "org-settings",
        code: "organization:settings",
        name: "Manage settings",
      },
      {
        id: "org-delete",
        code: "organization:delete",
        name: "Delete organization",
      },
    ],
  },
  {
    resource: "dashboard",
    items: [
      { id: "dash-read", code: "dashboard:read", name: "View dashboard" },
    ],
  },
  {
    resource: "users",
    items: [
      { id: "users-read", code: "users:read", name: "View employees" },
      { id: "users-invite", code: "users:invite", name: "Invite employees" },
      { id: "users-manage", code: "users:manage", name: "Manage employees" },
      { id: "users-profile", code: "users:profile", name: "Edit own profile" },
    ],
  },
  {
    resource: "roles",
    items: [
      { id: "roles-read", code: "roles:read", name: "View roles" },
      { id: "roles-manage", code: "roles:manage", name: "Manage roles" },
      { id: "perms-read", code: "permissions:read", name: "View permissions" },
    ],
  },
  {
    resource: "notifications",
    items: [
      {
        id: "notif-read",
        code: "notifications:read",
        name: "Read notifications",
      },
      {
        id: "notif-manage",
        code: "notifications:manage",
        name: "Manage notifications",
      },
    ],
  },
  {
    resource: "audit",
    items: [
      { id: "audit-read", code: "audit:read", name: "View audit log" },
      { id: "audit-export", code: "audit:export", name: "Export audit log" },
    ],
  },
  {
    resource: "workspace",
    items: [
      { id: "ws-read", code: "workspace:read", name: "View own workspace" },
      {
        id: "ws-manage",
        code: "workspace:manage",
        name: "Manage own workspace",
      },
    ],
  },
  {
    resource: "invitations",
    items: [
      { id: "inv-read", code: "invitations:read", name: "View invitations" },
      {
        id: "inv-manage",
        code: "invitations:manage",
        name: "Manage invitations",
      },
    ],
  },
  {
    resource: "sessions",
    items: [
      { id: "sess-read", code: "sessions:read", name: "View sessions" },
      { id: "sess-manage", code: "sessions:manage", name: "Manage sessions" },
    ],
  },
  {
    resource: "events",
    items: [{ id: "evt-read", code: "events:read", name: "View events" }],
  },
  {
    resource: "search",
    items: [
      { id: "search-global", code: "search:global", name: "Global search" },
    ],
  },
  {
    resource: "ai",
    items: [{ id: "ai-use", code: "ai:use", name: "Use AI Companion" }],
  },
  {
    resource: "employees",
    items: [
      {
        id: "emp-read",
        code: "employees:read",
        name: "View employee directory",
      },
      {
        id: "emp-profile",
        code: "employees:profile",
        name: "View own profile",
      },
      { id: "emp-manage", code: "employees:manage", name: "Manage employees" },
      {
        id: "emp-hire",
        code: "employees:hire",
        name: "Create employee records",
      },
    ],
  },
  {
    resource: "department",
    items: [
      { id: "dept-read", code: "department:read", name: "View departments" },
      {
        id: "dept-manage",
        code: "department:manage",
        name: "Manage departments",
      },
    ],
  },
  {
    resource: "team",
    items: [
      { id: "team-read", code: "team:read", name: "View teams" },
      { id: "team-manage", code: "team:manage", name: "Manage teams" },
    ],
  },
  {
    resource: "orgchart",
    items: [
      {
        id: "chart-read",
        code: "orgchart:read",
        name: "View organization chart",
      },
    ],
  },
  {
    resource: "expertise",
    items: [
      {
        id: "expertise-read",
        code: "expertise:read",
        name: "View skills and expertise",
      },
    ],
  },
  {
    resource: "presence",
    items: [
      {
        id: "presence-read",
        code: "presence:read",
        name: "View presence and availability",
      },
    ],
  },
  {
    resource: "favorites",
    items: [
      { id: "fav-manage", code: "favorites:manage", name: "Manage favorites" },
    ],
  },
  {
    resource: "intelligence",
    items: [
      {
        id: "intel-read",
        code: "intelligence:read",
        name: "View background intelligence",
      },
      {
        id: "intel-manage",
        code: "intelligence:manage",
        name: "Run workers and manage insights",
      },
    ],
  },
  {
    resource: "knowledge",
    items: [
      { id: "kb-read", code: "knowledge:read", name: "View knowledge items" },
      { id: "kb-search", code: "knowledge:search", name: "Search knowledge" },
      {
        id: "kb-manage",
        code: "knowledge:manage",
        name: "Create and edit knowledge",
      },
      {
        id: "kb-approve",
        code: "knowledge:approve",
        name: "Approve knowledge workflows",
      },
    ],
  },
  {
    resource: "learning",
    items: [
      {
        id: "learn-read",
        code: "learning:read",
        name: "View learning, courses and progress",
      },
      {
        id: "learn-manage",
        code: "learning:manage",
        name: "Manage courses, paths and academies",
      },
    ],
  },
  {
    resource: "hr",
    items: [
      {
        id: "hr-read",
        code: "hr:read",
        name: "View HR, leave, attendance and people operations",
      },
      {
        id: "hr-manage",
        code: "hr:manage",
        name: "Manage HR records, approvals and lifecycles",
      },
    ],
  },
  {
    resource: "payroll",
    items: [
      {
        id: "payroll-read",
        code: "payroll:read",
        name: "View payroll providers and run references",
      },
      {
        id: "payroll-manage",
        code: "payroll:manage",
        name: "Configure providers and record payroll runs",
      },
    ],
  },
  {
    resource: "crm",
    items: [
      {
        id: "crm-read",
        code: "crm:read",
        name: "View customers, CRM records and analytics",
      },
      {
        id: "crm-manage",
        code: "crm:manage",
        name: "Create and manage customers, leads, deals and support",
      },
    ],
  },
  {
    resource: "communication",
    items: [
      {
        id: "comm-read",
        code: "communication:read",
        name: "View communities and discussions",
      },
      {
        id: "comm-manage",
        code: "communication:manage",
        name: "Manage communities and content",
      },
    ],
  },
  {
    resource: "finance",
    items: [
      {
        id: "fin-read",
        code: "finance:read",
        name: "View finance, budgets, expenses and reports",
      },
      {
        id: "fin-manage",
        code: "finance:manage",
        name: "Create and manage budgets, expenses, procurement, vendors, invoices and forecasts",
      },
    ],
  },
  {
    resource: "executive",
    items: [
      {
        id: "exec-view",
        code: "executive:view",
        name: "View executive intelligence",
      },
      {
        id: "exec-manage",
        code: "executive:manage",
        name: "Run simulations and manage strategy",
      },
    ],
  },
  {
    resource: "enterprise",
    items: [
      {
        id: "ent-read",
        code: "enterprise:read",
        name: "View enterprise console",
      },
      {
        id: "ent-manage",
        code: "enterprise:manage",
        name: "Manage enterprise platform",
      },
      {
        id: "ident-manage",
        code: "identity:manage",
        name: "Manage SSO, SCIM and MFA",
      },
      { id: "plugins-manage", code: "plugins:manage", name: "Manage plugins" },
      {
        id: "marketplace-manage",
        code: "marketplace:manage",
        name: "Manage marketplace",
      },
      {
        id: "apikeys-manage",
        code: "api_keys:manage",
        name: "Manage API keys and gateway",
      },
      {
        id: "integrations-manage",
        code: "integrations:manage",
        name: "Manage integrations",
      },
      {
        id: "monitoring-read",
        code: "monitoring:read",
        name: "View monitoring",
      },
      {
        id: "observability-read",
        code: "observability:read",
        name: "View logs and traces",
      },
      {
        id: "security-manage",
        code: "security:manage",
        name: "Manage security center",
      },
      {
        id: "compliance-manage",
        code: "compliance:manage",
        name: "Manage compliance",
      },
      {
        id: "licenses-manage",
        code: "licenses:manage",
        name: "Manage licensing",
      },
      {
        id: "flags-manage",
        code: "feature_flags:manage",
        name: "Manage feature flags",
      },
    ],
  },
  {
    resource: "industry",
    items: [
      {
        id: "industry-read",
        code: "industry:read",
        name: "View industry solutions and catalog",
      },
      {
        id: "industry-manage",
        code: "industry:manage",
        name: "Manage industry packs, workflows and configurations",
      },
    ],
  },
  {
    resource: "digital_twin",
    items: [
      {
        id: "twin-read",
        code: "digital_twin:read",
        name: "View the digital twin, health and intelligence",
      },
      {
        id: "twin-manage",
        code: "digital_twin:manage",
        name: "Refresh the twin, generate predictions and run simulations",
      },
    ],
  },
  {
    resource: "developers",
    items: [
      {
        id: "dev-read",
        code: "developers:read",
        name: "View the developer portal and applications",
      },
      {
        id: "dev-manage",
        code: "developers:manage",
        name: "Manage applications, API keys and subscriptions",
      },
      {
        id: "webhooks-manage",
        code: "webhooks:manage",
        name: "Manage webhook endpoints and deliveries",
      },
      { id: "agents-read", code: "agents:read", name: "View AI agents" },
      {
        id: "agents-manage",
        code: "agents:manage",
        name: "Create and install AI agents",
      },
      {
        id: "marketplace-read",
        code: "marketplace:read",
        name: "Browse the marketplace",
      },
      {
        id: "marketplace-install",
        code: "marketplace:install",
        name: "Install extensions",
      },
      {
        id: "theme-manage",
        code: "theme:manage",
        name: "Manage branding themes",
      },
    ],
  },
  {
    resource: "governance",
    items: [
      {
        id: "gov-read",
        code: "governance:read",
        name: "View scopes, assignments, delegations and approval policies",
      },
      {
        id: "gov-manage",
        code: "governance:manage",
        name: "Create scopes, assign scoped roles, delegate and revoke authority, manage approval policies",
      },
    ],
  },
];
