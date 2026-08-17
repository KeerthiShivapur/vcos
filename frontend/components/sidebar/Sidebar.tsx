"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ArrowLeftRight,
  Banknote,
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Boxes,
  Brain,
  Briefcase,
  Building2,
  CalendarDays,
  CalendarHeart,
  CheckSquare2,
  Clock,
  FileText,
  Fingerprint,
  Flag,
  FolderKanban,
  Handshake,
  Headset,
  HeartPulse,
  Home,
  KeyRound,
  LayoutGrid,
  Lightbulb,
  ListChecks,
  ListTodo,
  Map,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  Network,
  Newspaper,
  Package,
  Palette,
  PieChart,
  Plane,
  Play,
  ScanSearch,
  ScrollText,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Store,
  Target,
  TrendingUp,
  Trophy,
  UserCircle2,
  UserPlus,
  Users,
  UserSquare2,
  Video,
  Vote,
  Wallet,
  Columns3,
  Stamp,
  Scale,
} from "lucide-react";
import { classNames } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { Badge } from "@/components/ui/Badge";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  permission?: string;
  badge?: number;
}

export function Sidebar({ unread }: { unread: number }) {
  const pathname = usePathname();
  const { user } = useAuth();

  const workspace: NavItem[] = [
    { href: "/home", label: "Home", icon: Home },
    { href: "/workspace", label: "My Workspace", icon: LayoutGrid },
    { href: "/notifications", label: "Notifications", icon: Bell, badge: unread },
    { href: "/ai", label: "AI Companion", icon: Sparkles, permission: PERMISSIONS.AI_USE },
  ];

  const company: NavItem[] = [
    { href: "/settings?tab=organization", label: "Organization", icon: Building2, permission: PERMISSIONS.ORGANIZATION_READ },
    { href: "/settings?tab=members", label: "Members", icon: UserCircle2, permission: PERMISSIONS.USERS_READ },
    { href: "/settings?tab=roles", label: "Roles & Permissions", icon: ShieldCheck, permission: PERMISSIONS.ROLES_READ },
    { href: "/settings?tab=audit", label: "Audit Log", icon: ScanSearch, permission: PERMISSIONS.AUDIT_READ },
    { href: "/settings?tab=sessions", label: "Sessions", icon: Settings },
    { href: "/governance", label: "Governance", icon: ShieldCheck, permission: PERMISSIONS.GOVERNANCE_READ },
  ];

  const people: NavItem[] = [
    { href: "/people", label: "People", icon: Users, permission: PERMISSIONS.EMPLOYEES_READ },
    { href: "/organization", label: "Organization", icon: Network, permission: PERMISSIONS.ORGCHART_READ },
    { href: "/departments", label: "Departments", icon: Building2, permission: PERMISSIONS.DEPARTMENT_READ },
    { href: "/teams", label: "Teams", icon: UserSquare2, permission: PERMISSIONS.TEAM_READ },
  ];

  const hr: NavItem[] = [
    { href: "/hr", label: "People Operations", icon: Users, permission: PERMISSIONS.HR_READ },
    { href: "/hr?tab=attendance", label: "Attendance", icon: Clock, permission: PERMISSIONS.HR_READ },
    { href: "/hr?tab=leave", label: "Leave", icon: Plane, permission: PERMISSIONS.HR_READ },
    { href: "/hr?tab=hiring", label: "Hiring", icon: Briefcase, permission: PERMISSIONS.HR_MANAGE },
    { href: "/hr?tab=performance", label: "Performance", icon: Target, permission: PERMISSIONS.HR_MANAGE },
    { href: "/hr?tab=payroll", label: "Payroll", icon: Banknote, permission: PERMISSIONS.PAYROLL_READ },
  ];

  const work: NavItem[] = [
    { href: "/projects", label: "Projects", icon: FolderKanban, permission: PERMISSIONS.PROJECTS_READ },
    { href: "/board", label: "Board", icon: Columns3, permission: PERMISSIONS.TASKS_READ },
    { href: "/tasks", label: "Tasks", icon: CheckSquare2, permission: PERMISSIONS.TASKS_READ },
    { href: "/approvals", label: "Approvals", icon: Stamp, permission: PERMISSIONS.APPROVALS_READ },
    { href: "/risks", label: "Risks", icon: ShieldAlert, permission: PERMISSIONS.RISKS_READ },
    { href: "/calendar", label: "Calendar", icon: CalendarDays, permission: PERMISSIONS.CALENDAR_READ },
    { href: "/meetings", label: "Meetings", icon: Users, permission: PERMISSIONS.MEETINGS_READ },
    { href: "/rooms", label: "Virtual Office", icon: Building2, permission: PERMISSIONS.MEETINGS_READ },
    { href: "/recordings", label: "Recordings", icon: Video, permission: PERMISSIONS.MEETINGS_READ },
    { href: "/goals", label: "Goals", icon: Target, permission: PERMISSIONS.GOALS_READ },
    { href: "/my-work", label: "My Work", icon: ListTodo, permission: PERMISSIONS.WORKLOAD_READ },
    { href: "/analytics", label: "Executive Analytics", icon: BarChart3, permission: PERMISSIONS.ANALYTICS_READ },
  ];

  const executive: NavItem[] = [
    { href: "/executive", label: "Executive Intelligence", icon: BarChart3, permission: PERMISSIONS.EXECUTIVE_VIEW },
    { href: "/intelligence", label: "Background Intelligence", icon: Brain, permission: PERMISSIONS.INTELLIGENCE_READ },
  ];

  const twin: NavItem[] = [
    { href: "/twin", label: "Digital Twin", icon: Activity, permission: PERMISSIONS.DIGITAL_TWIN_READ },
    { href: "/twin?tab=health", label: "Company Health", icon: HeartPulse, permission: PERMISSIONS.DIGITAL_TWIN_READ },
    { href: "/twin?tab=predictions", label: "Predictions", icon: TrendingUp, permission: PERMISSIONS.DIGITAL_TWIN_READ },
    { href: "/twin?tab=simulations", label: "Simulations", icon: Play, permission: PERMISSIONS.DIGITAL_TWIN_READ },
    { href: "/twin?tab=recommendations", label: "Recommendations", icon: CheckSquare2, permission: PERMISSIONS.DIGITAL_TWIN_READ },
    { href: "/twin?tab=decisions", label: "Decisions", icon: Network, permission: PERMISSIONS.DIGITAL_TWIN_READ },
    { href: "/twin?tab=brief", label: "Morning Brief", icon: Newspaper, permission: PERMISSIONS.DIGITAL_TWIN_READ },
  ];

  const developers: NavItem[] = [
    { href: "/developers", label: "Developer Portal", icon: Boxes, permission: PERMISSIONS.DEVELOPERS_READ },
    { href: "/developers?tab=apps", label: "Applications", icon: Package, permission: PERMISSIONS.DEVELOPERS_READ },
    { href: "/developers?tab=agents", label: "AI Agents", icon: Bot, permission: PERMISSIONS.AGENTS_READ },
    { href: "/developers?tab=marketplace", label: "Marketplace", icon: Store, permission: PERMISSIONS.MARKETPLACE_READ },
    { href: "/developers?tab=webhooks", label: "Webhooks", icon: ArrowLeftRight, permission: PERMISSIONS.WEBHOOKS_MANAGE },
    { href: "/developers?tab=themes", label: "Themes", icon: Palette, permission: PERMISSIONS.THEME_MANAGE },
    { href: "/developers?tab=billing", label: "Billing", icon: Banknote, permission: PERMISSIONS.DEVELOPERS_READ },
  ];

  const customers: NavItem[] = [
    { href: "/customers", label: "Customers", icon: Handshake, permission: PERMISSIONS.CRM_READ },
    { href: "/customers?tab=leads", label: "Leads", icon: UserPlus, permission: PERMISSIONS.CRM_READ },
    { href: "/customers?tab=pipeline", label: "Pipeline", icon: PieChart, permission: PERMISSIONS.CRM_READ },
    { href: "/customers?tab=contracts", label: "Contracts", icon: FileText, permission: PERMISSIONS.CRM_READ },
    { href: "/customers?tab=support", label: "Support", icon: Headset, permission: PERMISSIONS.CRM_READ },
    { href: "/customers?tab=partners", label: "Partners", icon: Handshake, permission: PERMISSIONS.CRM_READ },
    { href: "/customers?tab=analytics", label: "CRM Analytics", icon: BarChart3, permission: PERMISSIONS.CRM_READ },
  ];

  const finance: NavItem[] = [
    { href: "/finance", label: "Finance", icon: Banknote, permission: PERMISSIONS.FINANCE_READ },
    { href: "/finance?tab=budgets", label: "Budgets", icon: PieChart, permission: PERMISSIONS.FINANCE_READ },
    { href: "/finance?tab=expenses", label: "Expenses", icon: Wallet, permission: PERMISSIONS.FINANCE_READ },
    { href: "/finance?tab=procurement", label: "Procurement", icon: Package, permission: PERMISSIONS.FINANCE_READ },
    { href: "/finance?tab=vendors", label: "Vendors", icon: Handshake, permission: PERMISSIONS.FINANCE_READ },
    { href: "/finance?tab=invoices", label: "Invoices", icon: FileText, permission: PERMISSIONS.FINANCE_READ },
    { href: "/finance?tab=forecasting", label: "Forecasting", icon: TrendingUp, permission: PERMISSIONS.FINANCE_READ },
  ];

  const learning: NavItem[] = [
    { href: "/learning", label: "Learning Center", icon: BookOpen, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=courses", label: "Courses", icon: BookOpen, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=paths", label: "Learning Paths", icon: Map, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=skills", label: "Skills", icon: Brain, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=assessments", label: "Assessments", icon: CheckSquare2, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=certifications", label: "Certifications", icon: Trophy, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=mentorship", label: "Mentorship", icon: Users, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=career", label: "Career", icon: Target, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=academies", label: "Academies", icon: Building2, permission: PERMISSIONS.LEARNING_READ },
    { href: "/learning?tab=onboarding", label: "Onboarding", icon: UserSquare2, permission: PERMISSIONS.LEARNING_READ },
  ];

  const knowledge: NavItem[] = [
    { href: "/knowledge", label: "Knowledge Hub", icon: FileText, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/knowledge/workspace", label: "Knowledge Intelligence", icon: Brain, permission: PERMISSIONS.INTELLIGENCE_READ },
    { href: "/documents", label: "Documents", icon: FileText, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/wiki", label: "Wiki", icon: BookOpen, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/policies", label: "Policies", icon: ShieldCheck, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/sops", label: "SOPs", icon: ListChecks, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/templates", label: "Templates", icon: LayoutGrid, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/decisions", label: "Decisions", icon: Network, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/knowledge/graph", label: "Knowledge Graph", icon: Network, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/knowledge/analytics", label: "Knowledge Analytics", icon: BarChart3, permission: PERMISSIONS.KNOWLEDGE_READ },
    { href: "/collaboration", label: "Work Collaboration", icon: Network, permission: PERMISSIONS.BRAIN_READ },
    { href: "/capabilities", label: "Capability Center", icon: Boxes, permission: PERMISSIONS.BRAIN_READ },
    { href: "/people-decisions", label: "People Decisions", icon: Scale, permission: PERMISSIONS.BRAIN_READ },
    { href: "/execution", label: "Execution Center", icon: Activity, permission: PERMISSIONS.BRAIN_READ },
  ];

  const community: NavItem[] = [
    { href: "/communities", label: "Communities", icon: Users, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/feed", label: "Feed", icon: Newspaper, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/announcements", label: "Announcements", icon: Megaphone, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/forums", label: "Forums", icon: MessageSquare, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/recognition", label: "Recognition", icon: Trophy, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/innovation", label: "Innovation", icon: Lightbulb, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/polls", label: "Polls", icon: Vote, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/events", label: "Events", icon: CalendarHeart, permission: PERMISSIONS.COMMUNICATION_READ },
    { href: "/messages", label: "Messages", icon: MessagesSquare, permission: PERMISSIONS.COMMUNICATION_READ },
  ];

  const enterprise: NavItem[] = [
    { href: "/enterprise", label: "Enterprise Console", icon: Building2, permission: PERMISSIONS.ENTERPRISE_READ },
    { href: "/enterprise?tab=identity", label: "Identity & SSO", icon: Fingerprint, permission: PERMISSIONS.IDENTITY_MANAGE },
    { href: "/enterprise?tab=plugins", label: "Plugins", icon: Boxes, permission: PERMISSIONS.ENTERPRISE_READ },
    { href: "/enterprise?tab=marketplace", label: "Marketplace", icon: Store, permission: PERMISSIONS.ENTERPRISE_READ },
    { href: "/enterprise?tab=gateway", label: "API Gateway", icon: KeyRound, permission: PERMISSIONS.API_KEYS_MANAGE },
    { href: "/enterprise?tab=integrations", label: "Integrations", icon: ArrowLeftRight, permission: PERMISSIONS.INTEGRATIONS_MANAGE },
    { href: "/enterprise?tab=monitoring", label: "Monitoring", icon: Activity, permission: PERMISSIONS.MONITORING_READ },
    { href: "/enterprise?tab=observability", label: "Observability", icon: ScrollText, permission: PERMISSIONS.OBSERVABILITY_READ },
    { href: "/enterprise?tab=security", label: "Security Center", icon: ShieldCheck, permission: PERMISSIONS.SECURITY_MANAGE },
    { href: "/enterprise?tab=compliance", label: "Compliance", icon: ShieldAlert, permission: PERMISSIONS.COMPLIANCE_MANAGE },
    { href: "/enterprise?tab=licensing", label: "Licensing", icon: Package, permission: PERMISSIONS.LICENSES_MANAGE },
    { href: "/enterprise?tab=flags", label: "Feature Flags", icon: Flag, permission: PERMISSIONS.FEATURE_FLAGS_MANAGE },
    { href: "/enterprise?tab=ai", label: "Governed AI", icon: Bot, permission: PERMISSIONS.ENTERPRISE_READ },
  ];

  const industry: NavItem[] = [
    { href: "/industry", label: "Industry Solutions", icon: Boxes, permission: PERMISSIONS.INDUSTRY_READ },
    { href: "/industry?tab=catalog", label: "Pack Catalog", icon: Store, permission: PERMISSIONS.INDUSTRY_READ },
    { href: "/industry?tab=workflows", label: "Workflows", icon: ListChecks, permission: PERMISSIONS.INDUSTRY_READ },
  ];

  function isActive(href: string): boolean {
    if (href.startsWith("/settings")) return pathname.startsWith("/settings");
    if (href === "/people") return pathname === "/people" || pathname.startsWith("/people/");
    if (href === "/departments") return pathname === "/departments" || pathname.startsWith("/departments/");
    if (href === "/teams") return pathname === "/teams" || pathname.startsWith("/teams/");
    if (href === "/hr") return pathname === "/hr" || pathname.startsWith("/hr/");
    if (href === "/projects") return pathname === "/projects" || pathname.startsWith("/projects/");
    if (href === "/tasks") return pathname === "/tasks" || pathname.startsWith("/tasks/");
    if (href === "/goals") return pathname === "/goals" || pathname.startsWith("/goals/");
    if (href === "/meetings") return pathname === "/meetings" || pathname.startsWith("/meetings/");
if (href === "/rooms") return pathname === "/rooms" || pathname.startsWith("/rooms/");
if (href === "/recordings") return pathname === "/recordings" || pathname.startsWith("/recordings/");
    if (href === "/knowledge") return pathname === "/knowledge" || pathname.startsWith("/knowledge/");
    if (href === "/collaboration") return pathname === "/collaboration" || pathname.startsWith("/collaboration/");
    if (href === "/capabilities") return pathname === "/capabilities" || pathname.startsWith("/capabilities/");
    if (href === "/people-decisions")
      return pathname === "/people-decisions" || pathname.startsWith("/people-decisions/");
    if (href === "/execution") return pathname === "/execution" || pathname.startsWith("/execution/");
    if (href === "/learning" || href.startsWith("/learning?"))
      return pathname === "/learning" || pathname.startsWith("/learning/");
    if (href === "/documents") return pathname === "/documents" || pathname.startsWith("/documents/");
    if (href === "/wiki") return pathname === "/wiki" || pathname.startsWith("/wiki/");
    if (href === "/policies") return pathname === "/policies" || pathname.startsWith("/policies/");
    if (href === "/sops") return pathname === "/sops" || pathname.startsWith("/sops/");
    if (href === "/templates") return pathname === "/templates" || pathname.startsWith("/templates/");
    if (href === "/decisions") return pathname === "/decisions" || pathname.startsWith("/decisions/");
    if (href === "/communities") return pathname === "/communities" || pathname.startsWith("/communities/");
    if (href === "/forums") return pathname === "/forums" || pathname.startsWith("/forums/");
    if (href === "/customers" || href.startsWith("/customers?"))
      return pathname === "/customers" || pathname.startsWith("/customers/");
    if (href === "/finance" || href.startsWith("/finance?"))
      return pathname === "/finance" || pathname.startsWith("/finance/");
    if (href === "/enterprise" || href.startsWith("/enterprise?"))
      return pathname === "/enterprise" || pathname.startsWith("/enterprise/");
    if (href === "/industry" || href.startsWith("/industry?"))
      return pathname === "/industry" || pathname.startsWith("/industry/");
    if (href === "/twin" || href.startsWith("/twin?")) return pathname === "/twin";
    if (href === "/developers" || href.startsWith("/developers?")) return pathname === "/developers";
    return pathname === href;
  }

  function renderGroup(title: string, items: NavItem[]) {
    const visible = items.filter(
      (item) => !item.permission || roleCan(user?.role, item.permission as never)
    );
    if (visible.length === 0) return null;
    return (
      <div className="mt-6">
        <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-faint">{title}</p>
        <nav className="mt-1.5 flex flex-col gap-0.5">
          {visible.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={classNames(
                "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                isActive(item.href)
                  ? "bg-brand-soft text-brand"
                  : "text-muted hover:bg-surface hover:text-ink"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{item.label}</span>
              {item.badge !== undefined && item.badge > 0 && (
                <Badge tone="brand">{item.badge}</Badge>
              )}
            </Link>
          ))}
        </nav>
      </div>
    );
  }

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-line px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand text-white">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-bold tracking-tight text-ink">VCOS</p>
          <p className="text-[10px] font-medium uppercase tracking-wider text-faint">Company OS</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {renderGroup("Workspace", workspace)}
        {renderGroup("People", people)}
        {renderGroup("HR", hr)}
        {renderGroup("Work", work)}
        {renderGroup("Customers", customers)}
        {renderGroup("Finance", finance)}
        {renderGroup("Enterprise", enterprise)}
        {renderGroup("Industry", industry)}
    { renderGroup("Executive", executive) }
    {renderGroup("Digital Twin", twin)}
    {renderGroup("Developers", developers)}
    {renderGroup("Learning", learning)}
        {renderGroup("Knowledge", knowledge)}
        {renderGroup("Community", community)}
        {renderGroup("Company", company)}
      </div>

      <div className="border-t border-line p-3">
        <Link
          href="/ai"
          className="flex items-center gap-2.5 rounded-lg bg-brand-soft px-3 py-2.5"
        >
          <Sparkles className="h-4 w-4 text-brand" />
          <div className="leading-tight">
            <p className="text-xs font-semibold text-brand">AI Companion</p>
            <p className="text-[10px] text-faint">Ask about your work</p>
          </div>
        </Link>
      </div>
    </aside>
  );
}
