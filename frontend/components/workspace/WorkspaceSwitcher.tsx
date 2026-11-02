"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronUp,
  X,
  Search,
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
  HelpCircle,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useAdaptiveNavigation } from "@/hooks/useAdaptiveNavigation";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { classNames } from "@/lib/utils";
import { Avatar } from "@/components/ui/Avatar";

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

const WORKSPACE_LIST = [
  {
    id: "executive",
    label: "Executive",
    icon: "executive",
    route: "/executive",
  },
  {
    id: "my-workspace",
    label: "My Workspace",
    icon: "my-workspace",
    route: "/workspace",
  },
  { id: "projects", label: "Projects", icon: "projects", route: "/projects" },
  { id: "tasks", label: "Tasks", icon: "tasks", route: "/tasks" },
  { id: "teams", label: "Teams", icon: "teams", route: "/teams" },
  { id: "people", label: "People", icon: "people", route: "/people" },
  {
    id: "organization",
    label: "Organization",
    icon: "organization",
    route: "/organization",
  },
  {
    id: "operations",
    label: "Operations",
    icon: "operations",
    route: "/operations",
  },
  { id: "finance", label: "Finance", icon: "finance", route: "/finance" },
  {
    id: "knowledge",
    label: "Knowledge",
    icon: "knowledge",
    route: "/knowledge",
  },
  {
    id: "integrations",
    label: "Integrations",
    icon: "integrations",
    route: "/integrations",
  },
  {
    id: "administration",
    label: "Administration",
    icon: "administration",
    route: "/settings",
  },
];

interface WorkspaceSwitcherProps {
  className?: string;
}

export function WorkspaceSwitcher({ className }: WorkspaceSwitcherProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, organization } = useAuth();
  const { visibleModules } = useAdaptiveNavigation();
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const currentWorkspace =
    WORKSPACE_LIST.find((w) => pathname.startsWith(w.route)) ||
    WORKSPACE_LIST[1];

  const filteredWorkspaces = WORKSPACE_LIST.filter((w) =>
    w.label.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const handleWorkspaceSelect = useCallback(
    (workspace: (typeof WORKSPACE_LIST)[0]) => {
      router.push(workspace.route);
      setIsOpen(false);
    },
    [router],
  );

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setIsOpen(false);
    }
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const CurrentIcon = WORKSPACE_ICONS[currentWorkspace.icon] || LayoutGrid;

  return (
    <div className={`relative ${className || ""}`}>
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-canvas text-muted hover:text-ink ${isOpen && "bg-canvas text-ink"}`}
        aria-label="Switch workspace"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        {currentWorkspace ? (
          <>
            <CurrentIcon className="h-5 w-5" />
            <span className="hidden lg:inline-flex ml-2 text-sm font-medium truncate max-w-[140px]">
              {currentWorkspace.label}
            </span>
            <ChevronUp className="h-4 w-4 ml-1 lg:hidden" />
          </>
        ) : (
          <LayoutGrid className="h-5 w-5" />
        )}
      </button>

      {isOpen && (
        <div
          ref={dropdownRef}
          className="absolute right-0 top-full z-50 mt-1.5 w-72 origin-top-right animate-in fade-in-0 zoom-in-95"
          role="listbox"
          aria-label="Workspaces"
        >
          <div className="rounded-xl border border-line bg-canvas shadow-popper overflow-hidden">
            {/* Search */}
            <div className="border-b border-line p-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search workspaces..."
                  className="w-full h-9 pl-9 pr-3 rounded-lg border border-line bg-surface text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  autoFocus
                />
              </div>
            </div>

            {/* Workspace List */}
            <div className="max-h-[400px] overflow-y-auto">
              {filteredWorkspaces.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-faint">
                  No workspaces found
                </div>
              ) : (
                <ul role="listbox" className="py-1">
                  {filteredWorkspaces.map((workspace) => {
                    const IconComp =
                      WORKSPACE_ICONS[workspace.icon] || LayoutGrid;
                    return (
                      <li key={workspace.id} role="option">
                        <button
                          onClick={() => handleWorkspaceSelect(workspace)}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors ${
                            pathname.startsWith(workspace.route)
                              ? "bg-brand-soft text-brand"
                              : "text-muted hover:bg-canvas hover:text-ink"
                          }`}
                        >
                          <IconComp className="h-5 w-5 shrink-0" />
                          <span className="flex-1 truncate font-medium">
                            {workspace.label}
                          </span>
                          {pathname.startsWith(workspace.route) && (
                            <svg
                              className="h-4 w-4 text-brand"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M5 13l4 4L19 7"
                              />
                            </svg>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-line p-3">
              <button
                onClick={() => router.push("/settings?tab=workspaces")}
                className="w-full flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors"
              >
                <HelpCircle className="h-4 w-4" />
                <span>Manage workspaces</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function WorkspaceIndicator({ className }: { className?: string }) {
  const pathname = usePathname();
  const { visibleModules } = useAdaptiveNavigation();

  const currentWorkspace =
    WORKSPACE_LIST.find((w) => pathname.startsWith(w.route)) ||
    WORKSPACE_LIST[1];

  const CurrentIcon = WORKSPACE_ICONS[currentWorkspace.icon] || LayoutGrid;

  return (
    <span className={`flex items-center gap-1.5 ${className || ""}`}>
      {currentWorkspace ? (
        <CurrentIcon className="h-4 w-4" />
      ) : (
        <LayoutGrid className="h-4 w-4" />
      )}
    </span>
  );
}
