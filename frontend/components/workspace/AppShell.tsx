"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  LayoutGrid,
  Users,
  FolderKanban,
  CheckSquare2,
  Building2,
  Activity,
  Banknote,
  FileText,
  ArrowLeftRight,
  Settings,
  Search,
  Bell,
  ChevronDown,
  Menu,
  X,
  Sun,
  Moon,
  LogOut,
  User,
  HelpCircle,
  Grid,
  Sparkles,
  Command,
  Key,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useAdaptiveNavigation } from "@/hooks/useAdaptiveNavigation";
import { useWorkspace } from "./WorkspaceProvider";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Avatar } from "@/components/ui/Avatar";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";
import { classNames } from "@/lib/utils";

const WORKSPACE_ICONS: Record<
  string,
  React.ComponentType<{ className?: string }>
> = {
  executive: LayoutDashboard,
  "my-workspace": LayoutGrid,
  projects: FolderKanban,
  tasks: CheckSquare2,
  teams: Users,
  people: Users,
  organization: Building2,
  operations: Activity,
  finance: Banknote,
  knowledge: FileText,
  integrations: ArrowLeftRight,
  administration: Settings,
};

const NAVIGATION_GROUPS = [
  {
    label: "Core",
    items: [
      {
        id: "executive",
        label: "Executive",
        icon: "executive",
        route: "/executive",
        permission: "EXECUTIVE_VIEW",
      },
      {
        id: "my-workspace",
        label: "My Workspace",
        icon: "my-workspace",
        route: "/workspace",
        permission: "WORKSPACE_READ",
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        id: "projects",
        label: "Projects",
        icon: "projects",
        route: "/projects",
        permission: "PROJECTS_READ",
      },
      {
        id: "tasks",
        label: "Tasks",
        icon: "tasks",
        route: "/tasks",
        permission: "TASKS_READ",
      },
      {
        id: "teams",
        label: "Teams",
        icon: "teams",
        route: "/teams",
        permission: "TEAM_READ",
      },
      {
        id: "operations",
        label: "Operations",
        icon: "operations",
        route: "/operations",
        permission: "OPERATIONS_READ",
      },
    ],
  },
  {
    label: "People",
    items: [
      {
        id: "people",
        label: "People",
        icon: "people",
        route: "/people",
        permission: "EMPLOYEES_READ",
      },
      {
        id: "organization",
        label: "Organization",
        icon: "organization",
        route: "/organization",
        permission: "ORGCHART_READ",
      },
    ],
  },
  {
    label: "Intelligence",
    items: [
      {
        id: "knowledge",
        label: "Knowledge",
        icon: "knowledge",
        route: "/knowledge",
        permission: "KNOWLEDGE_READ",
      },
      {
        id: "finance",
        label: "Finance",
        icon: "finance",
        route: "/finance",
        permission: "FINANCE_READ",
      },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        id: "integrations",
        label: "Integrations",
        icon: "integrations",
        route: "/integrations",
        permission: "INTEGRATIONS_READ",
      },
      {
        id: "administration",
        label: "Administration",
        icon: "administration",
        route: "/settings",
        permission: "ADMIN_READ",
      },
    ],
  },
];

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, organization, logout } = useAuth();
  const { visibleModules } = useAdaptiveNavigation();
  const { currentWorkspace, availableWorkspaces } = useWorkspace();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const hasPermission = useCallback(
    (permission: string) => {
      if (!permission) return true;
      return (
        user?.permissions?.includes(permission) ||
        user?.role === "admin" ||
        user?.role === "owner"
      );
    },
    [user?.permissions, user?.role],
  );

  const visibleNavigation = NAVIGATION_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => hasPermission(item.permission)),
  })).filter((group) => group.items.length > 0);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      if (e.key === "Escape") {
        setGlobalSearchOpen(false);
        setCommandPaletteOpen(false);
        setNotificationsOpen(false);
        setUserMenuOpen(false);
        setSidebarOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") as "light" | "dark" | null;
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.classList.toggle("dark", savedTheme === "dark");
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === "light" ? "dark" : "light";
    setTheme(newTheme);
    localStorage.setItem("theme", newTheme);
    document.documentElement.classList.toggle("dark", newTheme === "dark");
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = (e.target as HTMLFormElement).querySelector("input")?.value;
    if (query) {
      router.push(`/search?q=${encodeURIComponent(query)}`);
      setGlobalSearchOpen(false);
    }
  };

  return (
    <div className="flex h-screen bg-background flex-col overflow-hidden">
      {/* Top Bar */}
      <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-line bg-canvas/80 backdrop-blur-sm px-4">
        {/* Mobile menu toggle */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="lg:hidden p-2 rounded-lg text-muted hover:text-ink hover:bg-canvas"
          aria-label="Toggle menu"
        >
          {sidebarOpen ? (
            <X className="h-5 w-5" />
          ) : (
            <Menu className="h-5 w-5" />
          )}
        </button>

        {/* Workspace Switcher */}
        <div className="flex-1 lg:flex-none">
          <WorkspaceSwitcher />
        </div>

        {/* Global Search */}
        <div className="hidden lg:flex lg:flex-1 max-w-xl">
          <form onSubmit={handleSearchSubmit} className="relative w-full">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              ref={searchInputRef}
              type="search"
              placeholder="Search... (⌘K)"
              className="w-full h-9 pl-9 pr-10 rounded-lg border border-line bg-surface text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              onFocus={() => setGlobalSearchOpen(true)}
              onBlur={() => setTimeout(() => setGlobalSearchOpen(false), 200)}
            />
            {globalSearchOpen && (
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-faint px-1.5 py-0.5 rounded bg-muted">
                <Key className="h-3 w-3" />
              </kbd>
            )}
          </form>
        </div>

        {/* Right side actions */}
        <div className="flex items-center gap-1">
          {/* Notifications */}
          <Dropdown
            trigger={(open) => (
              <button
                onClick={() => setNotificationsOpen(!open)}
                className="p-2 rounded-lg text-muted hover:text-ink hover:bg-canvas transition-colors"
                aria-label="Notifications"
              >
                <Bell className="h-5 w-5" />
              </button>
            )}
            // eslint-disable-next-line react/no-children-prop
            children={(close) => (
              <>
                <div className="p-3 border-b border-line">
                  <h3 className="font-medium text-ink">Notifications</h3>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  <div className="p-4 text-center text-sm text-faint">
                    No notifications
                  </div>
                </div>
                <div className="p-3 border-t border-line">
                  <button
                    className="w-full text-sm text-brand hover:text-brand-strong"
                    onClick={close}
                  >
                    View all notifications
                  </button>
                </div>
              </>
            )}
            align="right"
            className="w-80"
          />

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-muted hover:text-ink hover:bg-canvas transition-colors"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          >
            {theme === "light" ? (
              <Moon className="h-5 w-5" />
            ) : (
              <Sun className="h-5 w-5" />
            )}
          </button>

          {/* Command Palette Trigger */}
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="hidden lg:flex p-2 rounded-lg text-muted hover:text-ink hover:bg-canvas transition-colors"
            aria-label="Open command palette (⌘K)"
          >
            <Command className="h-5 w-5" />
            <kbd className="ml-1 text-xs text-faint px-1.5 py-0.5 rounded bg-muted">
              ⌘K
            </kbd>
          </button>

          {/* User Menu */}
          <Dropdown
            trigger={(open) => (
              <button
                onClick={() => setUserMenuOpen(!open)}
                className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-canvas transition-colors"
                aria-label="User menu"
              >
                <Avatar
                  name={user?.full_name}
                  src={user?.avatar_url}
                  size="sm"
                />
                <span className="hidden lg:block text-sm font-medium text-ink truncate max-w-[120px]">
                  {user?.full_name || "User"}
                </span>
                <ChevronDown className="h-4 w-4 text-muted lg:hidden" />
              </button>
            )}
            // eslint-disable-next-line react/no-children-prop
            children={(close) => (
              <>
                <div className="px-3 py-2 border-b border-line">
                  <p className="text-sm font-medium text-ink">
                    {user?.full_name}
                  </p>
                  <p className="text-xs text-faint truncate">{user?.email}</p>
                  {organization && (
                    <p className="text-xs text-faint truncate mt-1">
                      {organization.name}
                    </p>
                  )}
                </div>
                <MenuItem
                  onClick={() => {
                    router.push("/workspace?tab=profile");
                    close();
                  }}
                  icon={User}
                  label="Profile"
                />
                <MenuItem
                  onClick={() => {
                    router.push("/settings");
                    close();
                  }}
                  icon={Settings}
                  label="Settings"
                />
                <MenuItem
                  onClick={() => {
                    router.push("/help");
                    close();
                  }}
                  icon={HelpCircle}
                  label="Help & Support"
                />
                <div className="border-t border-line my-1" />
                <MenuItem
                  onClick={() => {
                    logout();
                    close();
                  }}
                  icon={LogOut}
                  label="Sign out"
                  danger
                />
              </>
            )}
            align="right"
            className="w-56"
          />
        </div>
      </header>

      {/* Mobile Search Bar */}
      <div
        className={`lg:hidden border-b border-line ${globalSearchOpen ? "block" : "hidden"}`}
      >
        <form onSubmit={handleSearchSubmit} className="p-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              ref={searchInputRef}
              type="search"
              placeholder="Search... (⌘K)"
              className="w-full h-10 pl-9 pr-3 rounded-lg border border-line bg-surface text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              autoFocus
            />
          </div>
        </form>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside
          ref={sidebarRef}
          className={`fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-in-out lg:relative lg:translate-x-0 border-r border-line bg-canvas ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
          aria-label="Main navigation"
        >
          <nav className="flex h-full flex-col p-3" role="navigation">
            <ul className="flex-1 overflow-y-auto space-y-4" role="list">
              {visibleNavigation.map((group) => (
                <li key={group.label}>
                  <h3 className="px-3 mb-1.5 text-xs font-semibold uppercase tracking-wider text-faint">
                    {group.label}
                  </h3>
                  <ul className="space-y-0.5" role="list">
                    {group.items.map((item) => {
                      const IconComp = WORKSPACE_ICONS[item.icon] || LayoutGrid;
                      const isActive = pathname.startsWith(item.route);
                      return (
                        <li key={item.id}>
                          <Link
                            href={item.route}
                            onClick={() => setSidebarOpen(false)}
                            className={classNames(
                              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                              isActive
                                ? "bg-brand-soft text-brand"
                                : "text-muted hover:bg-canvas hover:text-ink",
                            )}
                            aria-current={isActive ? "page" : undefined}
                          >
                            <IconComp className="h-5 w-5 shrink-0" />
                            <span className="truncate">{item.label}</span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>

            {/* Sidebar Footer */}
            <div className="border-t border-line pt-3">
              <Link
                href="/settings"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-muted hover:bg-canvas hover:text-ink transition-colors"
              >
                <Settings className="h-5 w-5" />
                <span>Settings</span>
              </Link>
            </div>
          </nav>
        </aside>

        {/* Sidebar Overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/50 lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto lg:overflow-hidden" role="main">
          <div className="h-full lg:h-full">{children}</div>
        </main>
      </div>

      {/* Command Palette */}
      {commandPaletteOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-20"
          onClick={() => setCommandPaletteOpen(false)}
        >
          <div
            className="w-full max-w-2xl bg-canvas rounded-xl border border-line shadow-popper overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative p-3 border-b border-line">
              <Command className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
              <input
                type="text"
                placeholder="Type a command or search... (⌘K)"
                className="w-full h-10 pl-10 pr-3 rounded-lg border border-line bg-surface text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                autoFocus
              />
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-faint px-1.5 py-0.5 rounded bg-muted">
                <Key className="h-3 w-3" />
              </kbd>
            </div>
            <div className="max-h-[400px] overflow-y-auto p-3">
              <div className="mb-4">
                <h4 className="px-3 mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Workspaces
                </h4>
                {availableWorkspaces.map((workspace) => {
                  const IconComp = WORKSPACE_ICONS[workspace.id] || LayoutGrid;
                  const route = workspace.defaultRoute || workspace.routes[0];
                  return (
                    <button
                      key={workspace.id}
                      onClick={() => {
                        router.push(route);
                        setCommandPaletteOpen(false);
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left text-muted hover:bg-canvas hover:text-ink transition-colors"
                    >
                      <IconComp className="h-5 w-5" />
                      <span className="font-medium">{workspace.label}</span>
                    </button>
                  );
                })}
              </div>
              <div className="mb-4">
                <h4 className="px-3 mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Quick Actions
                </h4>
                <button
                  onClick={() => {
                    router.push("/projects/new");
                    setCommandPaletteOpen(false);
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left text-muted hover:bg-canvas hover:text-ink transition-colors"
                >
                  <Sparkles className="h-5 w-5" />
                  <span className="font-medium">Create Project</span>
                </button>
                <button
                  onClick={() => {
                    router.push("/tasks/new");
                    setCommandPaletteOpen(false);
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left text-muted hover:bg-canvas hover:text-ink transition-colors"
                >
                  <CheckSquare2 className="h-5 w-5" />
                  <span className="font-medium">Create Task</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
