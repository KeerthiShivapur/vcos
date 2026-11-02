"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Target,
  FolderKanban,
  Calendar,
  MessageSquare,
  Settings,
  HelpCircle,
  Menu,
  X,
  Bell,
  Search,
  ChevronDown,
  User,
  LogOut,
  Home,
  Briefcase,
  Flag,
  BookOpen,
  Clock,
  Activity,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { PWAInstallBanner } from "@/components/pwa/PWAInstallPrompt";

const NAV_ITEMS = [
  { id: "home", label: "Home", icon: Home, href: "/home" },
  {
    id: "workspace",
    label: "Workspace",
    icon: LayoutDashboard,
    href: "/workspace",
  },
  { id: "projects", label: "Projects", icon: Briefcase, href: "/projects" },
  { id: "tasks", label: "Tasks", icon: FolderKanban, href: "/tasks" },
  { id: "goals", label: "Goals", icon: Target, href: "/goals" },
  { id: "calendar", label: "Calendar", icon: Calendar, href: "/calendar" },
  { id: "people", label: "People", icon: Users, href: "/people" },
  { id: "decisions", label: "Decisions", icon: Activity, href: "/decisions" },
  {
    id: "collaboration",
    label: "Collaboration",
    icon: MessageSquare,
    href: "/collaboration",
  },
  { id: "knowledge", label: "Knowledge", icon: BookOpen, href: "/wiki" },
  { id: "analytics", label: "Analytics", icon: Activity, href: "/analytics" },
  { id: "settings", label: "Settings", icon: Settings, href: "/settings" },
];

const MOBILE_BOTTOM_NAV = [
  { id: "home", label: "Home", icon: Home, href: "/home" },
  {
    id: "workspace",
    label: "Workspace",
    icon: LayoutDashboard,
    href: "/workspace",
  },
  { id: "projects", label: "Projects", icon: Briefcase, href: "/projects" },
  { id: "tasks", label: "Tasks", icon: FolderKanban, href: "/tasks" },
  { id: "more", label: "More", icon: Menu, href: "#" },
];

export function MobileAppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuth();
  const { isSubscribed, subscribe, permission } = usePushNotifications();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  // Check online status
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    setIsOnline(navigator.onLine);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + K for command palette
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      // Escape to close modals
      if (e.key === "Escape") {
        setCommandPaletteOpen(false);
        setUserMenuOpen(false);
        setNotificationsOpen(false);
        setSidebarOpen(false);
      }
      // Cmd/Ctrl + B for sidebar toggle
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault();
        setSidebarOpen(!sidebarOpen);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [sidebarOpen]);

  // Close sidebar on mobile when navigating
  useEffect(() => {
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  }, [pathname]);

  const handleNavigation = useCallback(
    (href: string) => {
      router.push(href);
      if (window.innerWidth < 1024) {
        setSidebarOpen(false);
      }
    },
    [router],
  );

  const currentNavItem =
    NAV_ITEMS.find((item) => pathname.startsWith(item.href)) || NAV_ITEMS[0];

  return (
    <div className="min-h-screen bg-slate-50">
      {/* PWA Install Banner */}
      <PWAInstallBanner />

      {/* Offline Indicator */}
      {!isOnline && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-amber-600 text-white text-center py-2 text-sm font-medium shadow-lg animate-slide-down">
          You're offline. Changes will sync when you're back online.
        </div>
      )}

      {/* Mobile Header */}
      <header className="fixed top-0 left-0 right-0 z-40 bg-white border-b border-slate-200 lg:hidden">
        <div className="flex items-center justify-between h-16 px-4">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label="Open menu"
          >
            <Menu className="w-6 h-6" />
          </button>

          <div className="flex-1 text-center">
            <span className="font-semibold text-slate-900">VCOS</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setNotificationsOpen(true)}
              className="p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors relative"
              aria-label="Notifications"
            >
              <Bell className="w-5 h-5" />
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                3
              </span>
            </button>
            <button
              onClick={() => setUserMenuOpen(true)}
              className="p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
              aria-label="User menu"
            >
              <User className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Desktop Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 transform transition-transform duration-300 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Main navigation"
      >
        <div className="flex flex-col h-full">
          {/* Sidebar Header */}
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
                <LayoutDashboard className="w-5 h-5 text-indigo-600" />
              </div>
              <span className="font-bold text-xl text-slate-900">VCOS</span>
            </div>
          </div>

          {/* Navigation */}
          <nav
            className="flex-1 p-4 space-y-1 overflow-y-auto"
            aria-label="Main navigation"
          >
            {NAV_ITEMS.map((item) => {
              const isActive = pathname.startsWith(item.href);
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavigation(item.href)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                  aria-current={isActive ? "page" : undefined}
                >
                  <item.icon
                    className={`w-5 h-5 ${isActive ? "text-indigo-600" : "text-slate-400"}`}
                  />
                  {item.label}
                </button>
              );
            })}
          </nav>

          {/* User Section */}
          <div className="p-4 border-t border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
                <User className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-slate-900 truncate">
                  {user?.fullName || user?.email}
                </p>
                <p className="text-xs text-slate-500 truncate">{user?.email}</p>
              </div>
            </div>
          </div>
        </div>
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
      <main className="lg:ml-0 pt-16 lg:pt-0 min-h-screen">
        <div className="p-4 lg:p-6">{children}</div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-slate-200 lg:hidden">
        <div className="grid grid-cols-5 gap-1 px-2 py-2">
          {MOBILE_BOTTOM_NAV.map((item) => {
            const isActive =
              pathname.startsWith(item.href) && item.id !== "more";
            return (
              <button
                key={item.id}
                onClick={() =>
                  item.id === "more"
                    ? setSidebarOpen(true)
                    : handleNavigation(item.href)
                }
                className={`flex flex-col items-center gap-1 px-2 py-2 rounded-lg transition-colors ${
                  isActive
                    ? "text-indigo-600 bg-indigo-50"
                    : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                }`}
                aria-current={isActive ? "page" : undefined}
              >
                <item.icon
                  className={`w-6 h-6 ${isActive ? "text-indigo-600" : ""}`}
                />
                <span className="text-xs font-medium">{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* Command Palette */}
      {commandPaletteOpen && (
        <CommandPalette
          onClose={() => setCommandPaletteOpen(false)}
          onNavigate={handleNavigation}
        />
      )}

      {/* Notifications Panel */}
      {notificationsOpen && (
        <NotificationsPanel onClose={() => setNotificationsOpen(false)} />
      )}

      {/* User Menu */}
      {userMenuOpen && (
        <UserMenu onClose={() => setUserMenuOpen(false)} user={user} />
      )}

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}

// Command Palette Component
function CommandPalette({
  onClose,
  onNavigate,
}: {
  onClose: () => void;
  onNavigate: (href: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filteredItems = NAV_ITEMS.filter(
    (item) =>
      item.label.toLowerCase().includes(query.toLowerCase()) ||
      item.id.toLowerCase().includes(query.toLowerCase()),
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) =>
          Math.min(prev + 1, filteredItems.length - 1),
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredItems[selectedIndex]) {
          onNavigate(filteredItems[selectedIndex].href);
          onClose();
        }
      } else if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filteredItems, selectedIndex, onNavigate, onClose]);

  useEffect(() => {
    setSelectedIndex(0);
    const input = document.getElementById("command-palette-input");
    input?.focus();
  }, [query]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20">
      <div className="w-full max-w-2xl mx-4">
        <div className="bg-white rounded-xl shadow-xl border border-slate-200 overflow-hidden">
          <div className="relative p-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              id="command-palette-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type a command or search... (⌘K)"
              className="w-full pl-10 pr-4 py-3 text-lg bg-slate-50 border border-slate-200 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 focus:outline-none"
            />
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 px-2 py-1 text-xs bg-slate-100 text-slate-500 rounded">
              ⌘K
            </kbd>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {filteredItems.length === 0 ? (
              <div className="p-8 text-center text-slate-500">
                No results found
              </div>
            ) : (
              filteredItems.map((item, index) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onNavigate(item.href);
                    onClose();
                  }}
                  className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors ${
                    index === selectedIndex
                      ? "bg-indigo-50 text-indigo-700"
                      : ""
                  }`}
                >
                  <item.icon
                    className={`w-5 h-5 ${index === selectedIndex ? "text-indigo-600" : "text-slate-400"}`}
                  />
                  <span className="font-medium">{item.label}</span>
                  <span className="ml-auto text-xs text-slate-400">
                    {item.href}
                  </span>
                </button>
              ))
            )}
          </div>

          <div className="p-3 border-t border-slate-200 text-center text-xs text-slate-500">
            <kbd className="px-2 py-1 bg-slate-100 rounded">↑</kbd>{" "}
            <kbd className="px-2 py-1 bg-slate-100 rounded">↓</kbd> to navigate
            • <kbd className="px-2 py-1 bg-slate-100 rounded">↵</kbd> to select
            • <kbd className="px-2 py-1 bg-slate-100 rounded">Esc</kbd> to close
          </div>
        </div>
      </div>
    </div>
  );
}

// Notifications Panel
function NotificationsPanel({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed top-16 right-4 w-96 max-h-[600px] bg-white rounded-xl shadow-xl border border-slate-200 z-50 animate-slide-in">
      <div className="flex items-center justify-between p-4 border-b border-slate-200">
        <h3 className="font-semibold text-slate-900">Notifications</h3>
        <button
          onClick={onClose}
          className="p-2 text-slate-500 hover:text-slate-700 rounded-lg hover:bg-slate-100"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
      <div className="max-h-[500px] overflow-y-auto">
        <div className="p-4 space-y-3">
          {[
            {
              title: "New task assigned",
              body: "You have been assigned to 'Project Alpha'",
              time: "2 min ago",
              unread: true,
            },
            {
              title: "Meeting starting soon",
              body: "Team sync in 10 minutes",
              time: "15 min ago",
              unread: true,
            },
            {
              title: "Document updated",
              body: "Project requirements doc was updated",
              time: "1 hour ago",
              unread: false,
            },
          ].map((notif, i) => (
            <div
              key={i}
              className={`p-3 rounded-lg ${notif.unread ? "bg-indigo-50 border-l-4 border-indigo-500" : "hover:bg-slate-50"}`}
            >
              <p
                className={`font-medium ${notif.unread ? "text-slate-900" : "text-slate-700"}`}
              >
                {notif.title}
              </p>
              <p className="text-sm text-slate-500 mt-1">{notif.body}</p>
              <p className="text-xs text-slate-400 mt-2">{notif.time}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="p-4 border-t border-slate-200">
        <button className="w-full py-2 text-indigo-600 font-medium hover:text-indigo-700">
          View all notifications
        </button>
      </div>
    </div>
  );
}

// User Menu
function UserMenu({ onClose, user }: { onClose: () => void; user: any }) {
  return (
    <div className="fixed top-16 right-4 w-56 bg-white rounded-xl shadow-xl border border-slate-200 z-50 animate-slide-in">
      <div className="p-3 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
            <User className="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <p className="font-medium text-slate-900">
              {user?.fullName || user?.email}
            </p>
            <p className="text-xs text-slate-500">{user?.email}</p>
          </div>
        </div>
      </div>
      <nav className="py-2">
        {[
          { label: "Profile", icon: User, href: "/settings/profile" },
          {
            label: "Notifications",
            icon: Bell,
            href: "/settings/notifications",
          },
          { label: "Preferences", icon: Settings, href: "/settings" },
          { label: "Help", icon: HelpCircle, href: "/help" },
          {
            label: "Sign out",
            icon: LogOut,
            href: "/auth/logout",
            danger: true,
          },
        ].map((item) => (
          <button
            key={item.label}
            onClick={() => {
              onClose();
              window.location.href = item.href;
            }}
            className={`w-full flex items-center gap-3 px-3 py-2 text-sm ${item.danger ? "text-red-600 hover:bg-red-50" : "text-slate-700 hover:bg-slate-50"}`}
          >
            <item.icon className="w-5 h-5" />
            {item.label}
          </button>
        ))}
      </nav>
    </div>
  );
}

export default MobileAppShell;
