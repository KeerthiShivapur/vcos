"use client";

import Link from "next/link";
import { Zap, Moon, Sun, Github, X } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface NavItem {
  id: string;
  label: string;
  iconName: string;
  children: { id: string; label: string }[];
}

interface SidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  activeSection: string;
  navigate: (id: string) => void;
  filteredNav: NavItem[];
  iconMap: Record<string, React.ComponentType<{ className?: string }>>;
}

export function Sidebar({
  sidebarOpen,
  setSidebarOpen,
  theme,
  toggleTheme,
  searchQuery,
  setSearchQuery,
  activeSection,
  navigate,
  filteredNav,
  iconMap,
}: SidebarProps) {
  return (
    <aside className={`${sidebarOpen ? "translate-x-0" : "-translate-x-full"} fixed inset-y-0 left-0 z-40 w-72 lg:translate-x-0 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-transform duration-300 ease-in-out`}>
      <div className="flex flex-col h-full">
        <div className="p-6 border-b border-slate-200 dark:border-slate-800">
          <Link href="/docs/embedded-analytics" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-xl text-slate-900 dark:text-white">VCOS Analytics</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">Embedded Analytics Docs</p>
            </div>
          </Link>
          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={toggleTheme}
              className="flex-1 px-3 py-2 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              {theme === "light" ? (
                <> <Moon className="w-4 h-4 mr-1" /> Dark </>
              ) : (
                <> <Sun className="w-4 h-4 mr-1" /> Light </>
              )}
            </button>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="relative">
            <input
              type="text"
              placeholder="Search docs..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
            />
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-6">
          {filteredNav.map(group => {
            const IconComponent = iconMap[group.iconName];
            return (
              <div key={group.id}>
                <div className="flex items-center gap-2 px-2 py-1 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  <IconComponent className="w-4 h-4" />
                  {group.label}
                </div>
              <ul className="space-y-1 mt-1">
                {group.children.map(item => (
                  <li key={item.id}>
                    <button
                      onClick={() => navigate(item.id)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                        activeSection === item.id
                          ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-medium"
                          : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                      }`}
                    >
                      {item.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex flex-col gap-2">
            <Link href="https://github.com/vcos" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">
              <Github className="w-4 h-4" />
              <span>GitHub</span>
            </Link>
            <Link href="/app/embedded-analytics" className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
              <Zap className="w-4 h-4 mr-1" />
              Try Live Demo
            </Link>
          </div>
        </div>
      </div>
    </aside>
  );
}