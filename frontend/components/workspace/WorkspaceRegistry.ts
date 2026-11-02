"use client";

import type { ReactNode } from "react";
import type { CompanyExperienceProfile } from "@/types";
import {
  LayoutDashboard,
  LayoutGrid,
  FolderKanban,
  CheckSquare2,
  Users,
  Building2,
  Activity,
  Banknote,
  FileText,
  ArrowLeftRight,
  Settings,
  Sun,
  Target,
  CalendarDays,
  Star,
  Plus,
  ListTodo,
  UserSquare2,
  ShieldCheck,
  GitBranch,
  AlertTriangle,
  PieChart,
  Wallet,
  Package,
  BookOpen,
  Network,
  Boxes,
  UserCircle2,
  Search,
} from "lucide-react";

export interface WorkspaceDefinition {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  requiredPermissions?: string[];
  routes: string[];
  defaultRoute?: string;
  layout?: "standard" | "dense" | "dashboard";
  category:
    "core" | "operations" | "intelligence" | "administration" | "personal";
  order: number;
  visibleProfiles: CompanyExperienceProfile[];
  badge?: () => number | Promise<number>;
  shortcuts?: Array<{
    label: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    href: string;
  }>;
}

export const WORKSPACE_REGISTRY: WorkspaceDefinition[] = [
  {
    id: "executive",
    label: "Executive",
    icon: LayoutDashboard,
    description: "Executive intelligence and company overview",
    requiredPermissions: ["EXECUTIVE_VIEW"],
    routes: ["/executive", "/executive/*"],
    defaultRoute: "/executive",
    layout: "dashboard",
    category: "intelligence",
    order: 1,
    visibleProfiles: ["mid_market", "large_enterprise", "global_enterprise"],
    shortcuts: [
      {
        label: "Company Health",
        description: "View company health metrics",
        icon: Activity,
        href: "/executive?tab=health",
      },
      {
        label: "Strategic Objectives",
        description: "Track strategic objectives",
        icon: Target,
        href: "/executive?tab=objectives",
      },
      {
        label: "Workforce Capacity",
        description: "View workforce capacity",
        icon: Users,
        href: "/executive?tab=workforce",
      },
    ],
  },
  {
    id: "my-workspace",
    label: "My Workspace",
    icon: LayoutGrid,
    description: "Personal workspace with tasks, calendar, and priorities",
    requiredPermissions: ["WORKSPACE_READ"],
    routes: ["/workspace", "/workspace/*"],
    defaultRoute: "/workspace",
    layout: "standard",
    category: "personal",
    order: 2,
    visibleProfiles: [
      "startup",
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "My Day",
        description: "Daily operating surface",
        icon: Sun,
        href: "/workspace?tab=my-day",
      },
      {
        label: "My Tasks",
        description: "Tasks assigned to me",
        icon: CheckSquare2,
        href: "/workspace?tab=my-tasks",
      },
      {
        label: "My Calendar",
        description: "Schedule and meetings",
        icon: CalendarDays,
        href: "/workspace?tab=calendar",
      },
    ],
  },
  {
    id: "projects",
    label: "Projects",
    icon: FolderKanban,
    description: "Project portfolio and execution management",
    requiredPermissions: ["PROJECTS_READ"],
    routes: ["/projects", "/projects/*"],
    defaultRoute: "/projects",
    layout: "standard",
    category: "operations",
    order: 3,
    visibleProfiles: [
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "All Projects",
        description: "Browse all projects",
        icon: FolderKanban,
        href: "/projects",
      },
      {
        label: "My Projects",
        description: "Projects I'm involved in",
        icon: Star,
        href: "/projects?tab=my",
      },
      {
        label: "Create Project",
        description: "Start a new project",
        icon: Plus,
        href: "/projects/new",
      },
    ],
  },
  {
    id: "tasks",
    label: "Tasks",
    icon: CheckSquare2,
    description: "Task management and tracking",
    requiredPermissions: ["TASKS_READ"],
    routes: ["/tasks", "/tasks/*"],
    defaultRoute: "/tasks",
    layout: "standard",
    category: "operations",
    order: 4,
    visibleProfiles: [
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "My Tasks",
        description: "Tasks assigned to me",
        icon: ListTodo,
        href: "/tasks?tab=my",
      },
      {
        label: "Create Task",
        description: "Create a new task",
        icon: Plus,
        href: "/tasks/new",
      },
    ],
  },
  {
    id: "teams",
    label: "Teams",
    icon: Users,
    description: "Team management and collaboration",
    requiredPermissions: ["TEAM_READ"],
    routes: ["/teams", "/teams/*"],
    defaultRoute: "/teams",
    layout: "standard",
    category: "operations",
    order: 5,
    visibleProfiles: [
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "All Teams",
        description: "Browse all teams",
        icon: Users,
        href: "/teams",
      },
      {
        label: "Create Team",
        description: "Create a new team",
        icon: Plus,
        href: "/teams/new",
      },
    ],
  },
  {
    id: "people",
    label: "People",
    icon: Users,
    description: "People directory and profiles",
    requiredPermissions: ["EMPLOYEES_READ"],
    routes: ["/people", "/people/*"],
    defaultRoute: "/people",
    layout: "standard",
    category: "operations",
    order: 6,
    visibleProfiles: [
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "All People",
        description: "Browse all people",
        icon: Users,
        href: "/people",
      },
      {
        label: "Departments",
        description: "Browse departments",
        icon: Building2,
        href: "/departments",
      },
      {
        label: "Teams",
        description: "Browse teams",
        icon: UserSquare2,
        href: "/teams",
      },
    ],
  },
  {
    id: "organization",
    label: "Organization",
    icon: Building2,
    description: "Organization structure and administration",
    requiredPermissions: ["ORGCHART_READ"],
    routes: ["/organization", "/organization/*"],
    defaultRoute: "/organization",
    layout: "standard",
    category: "administration",
    order: 7,
    visibleProfiles: ["mid_market", "large_enterprise", "global_enterprise"],
    shortcuts: [
      {
        label: "Departments",
        description: "Browse departments",
        icon: Building2,
        href: "/organization?tab=departments",
      },
      {
        label: "Teams",
        description: "Browse teams",
        icon: UserSquare2,
        href: "/organization?tab=teams",
      },
      {
        label: "Roles",
        description: "Manage roles",
        icon: ShieldCheck,
        href: "/settings?tab=roles",
      },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    icon: Activity,
    description: "Operations workflows and department execution",
    requiredPermissions: ["OPERATIONS_READ"],
    routes: ["/operations", "/operations/*"],
    defaultRoute: "/operations",
    layout: "dense",
    category: "operations",
    order: 8,
    visibleProfiles: ["mid_market", "large_enterprise", "global_enterprise"],
    shortcuts: [
      {
        label: "Workflows",
        description: "Manage workflows",
        icon: GitBranch,
        href: "/operations?tab=workflows",
      },
      {
        label: "Pipelines",
        description: "View pipelines",
        icon: GitBranch,
        href: "/operations?tab=pipelines",
      },
      {
        label: "Blockers",
        description: "View blockers",
        icon: AlertTriangle,
        href: "/operations?tab=blockers",
      },
    ],
  },
  {
    id: "finance",
    label: "Finance",
    icon: Banknote,
    description: "Financial management and reporting",
    requiredPermissions: ["FINANCE_READ"],
    routes: ["/finance", "/finance/*"],
    defaultRoute: "/finance",
    layout: "dense",
    category: "operations",
    order: 9,
    visibleProfiles: ["mid_market", "large_enterprise", "global_enterprise"],
    shortcuts: [
      {
        label: "Budgets",
        description: "Manage budgets",
        icon: PieChart,
        href: "/finance?tab=budgets",
      },
      {
        label: "Expenses",
        description: "Track expenses",
        icon: Wallet,
        href: "/finance?tab=expenses",
      },
      {
        label: "Procurement",
        description: "Manage procurement",
        icon: Package,
        href: "/finance?tab=procurement",
      },
    ],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    icon: FileText,
    description: "Knowledge hub and documentation",
    requiredPermissions: ["KNOWLEDGE_READ"],
    routes: ["/knowledge", "/knowledge/*"],
    defaultRoute: "/knowledge",
    layout: "standard",
    category: "intelligence",
    order: 10,
    visibleProfiles: [
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "Documents",
        description: "Browse documents",
        icon: FileText,
        href: "/documents",
      },
      {
        label: "Wiki",
        description: "Company wiki",
        icon: BookOpen,
        href: "/wiki",
      },
      {
        label: "Decisions",
        description: "Decision registry",
        icon: Network,
        href: "/decisions",
      },
    ],
  },
  {
    id: "integrations",
    label: "Integrations",
    icon: ArrowLeftRight,
    description: "External integrations and connections",
    requiredPermissions: ["INTEGRATIONS_READ"],
    routes: ["/integrations", "/integrations/*"],
    defaultRoute: "/integrations",
    layout: "standard",
    category: "administration",
    order: 11,
    visibleProfiles: ["mid_market", "large_enterprise", "global_enterprise"],
    shortcuts: [
      {
        label: "Connected Apps",
        description: "Manage connected apps",
        icon: Boxes,
        href: "/integrations?tab=apps",
      },
      {
        label: "Add Integration",
        description: "Add new integration",
        icon: Plus,
        href: "/integrations/new",
      },
    ],
  },
  {
    id: "administration",
    label: "Administration",
    icon: Settings,
    description: "System administration and settings",
    requiredPermissions: ["ADMIN_READ"],
    routes: ["/settings", "/settings/*", "/enterprise", "/enterprise/*"],
    defaultRoute: "/settings",
    layout: "standard",
    category: "administration",
    order: 12,
    visibleProfiles: [
      "growing",
      "mid_market",
      "large_enterprise",
      "global_enterprise",
    ],
    shortcuts: [
      {
        label: "Organization",
        description: "Organization settings",
        icon: Building2,
        href: "/settings?tab=organization",
      },
      {
        label: "Members",
        description: "Manage members",
        icon: UserCircle2,
        href: "/settings?tab=members",
      },
      {
        label: "Roles",
        description: "Manage roles",
        icon: ShieldCheck,
        href: "/settings?tab=roles",
      },
      {
        label: "Audit Log",
        description: "View audit log",
        icon: Search,
        href: "/settings?tab=audit",
      },
    ],
  },
];

export function getVisibleWorkspaces(
  profile: CompanyExperienceProfile,
): WorkspaceDefinition[] {
  return WORKSPACE_REGISTRY.filter((w) =>
    w.visibleProfiles.includes(profile),
  ).sort((a, b) => a.order - b.order);
}

export function getWorkspaceById(id: string): WorkspaceDefinition | undefined {
  return WORKSPACE_REGISTRY.find((w) => w.id === id);
}

export function canAccessWorkspace(
  workspace: WorkspaceDefinition,
  userRole: string,
): boolean {
  if (
    !workspace.requiredPermissions ||
    workspace.requiredPermissions.length === 0
  )
    return true;
  if (userRole === "admin" || userRole === "owner" || userRole === "ceo")
    return true;
  return false;
}
