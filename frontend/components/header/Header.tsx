"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bookmark,
  Building2,
  Command,
  FileText,
  LogOut,
  Moon,
  Plus,
  Search,
  Settings2,
  Sparkles,
  Sun,
  User,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/hooks/useTheme";
import { Avatar } from "@/components/ui/Avatar";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";
import { NotificationBell } from "@/components/notifications/NotificationCenter";
import { CommandPalette } from "@/components/header/CommandPalette";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import { api } from "@/lib/api";

export function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, organization, logout, platform } = useAuth();
  const { theme, toggle } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);

  const quickActions = useMemo(
    () => [
      { label: "New note", description: "Save a quick note in your workspace", icon: FileText, href: "/workspace?new=note" },
      { label: "New bookmark", description: "Save a link for later", icon: Bookmark, href: "/workspace?new=bookmark" },
      { label: "New shortcut", description: "Pin a destination", icon: Plus, href: "/workspace?new=shortcut" },
    ],
    []
  );

  async function handleQuickCreate(href: string) {
    setQuickOpen(false);
    router.push(href);
  }

  return (
    <>
      <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-canvas/80 px-4 backdrop-blur">
        <button
          onClick={() => setPaletteOpen(true)}
          className="hidden h-9 flex-1 items-center gap-2.5 rounded-lg border border-line bg-surface px-3 text-left text-sm text-faint transition-colors hover:border-faint/40 md:flex md:max-w-md"
        >
          <Search className="h-4 w-4" />
          <span className="flex-1 truncate">Search the company…</span>
          <kbd className="flex items-center gap-0.5 rounded border border-line bg-canvas px-1.5 py-0.5 text-[10px] font-medium text-faint">
            <Command className="h-3 w-3" />K
          </kbd>
        </button>

        <button
          onClick={() => setPaletteOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-canvas hover:text-ink md:hidden"
          aria-label="Search"
        >
          <Search className="h-[18px] w-[18px]" />
        </button>

        <div className="flex-1 md:hidden" />

        <Dropdown
          align="left"
          width="w-64"
          trigger={(open) => (
            <span className={`flex h-9 items-center gap-2 rounded-lg px-2.5 transition-colors ${open ? "bg-canvas" : "hover:bg-canvas"}`}>
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand text-white">
                <Building2 className="h-3.5 w-3.5" />
              </span>
              <span className="hidden max-w-36 truncate text-[13px] font-semibold text-ink lg:block">
                {organization?.name ?? "Company"}
              </span>
            </span>
          )}
        >
          {(close) => (
            <>
              <div className="border-b border-line px-4 py-3">
                <p className="text-sm font-semibold text-ink">{organization?.name ?? "Company"}</p>
                <p className="text-xs text-faint">Managed on VCOS · {organization?.timezone ?? "UTC"}</p>
              </div>
              <MenuItem icon={Building2} label="Organization settings" onClick={() => { close(); router.push("/settings?tab=organization"); }} />
              <div className="px-3.5 py-2.5 text-[11px] text-faint">
                Phase 1 · {platform?.version ?? "1.0.0"} · {platform?.features.ai_foundation ? "AI foundation" : ""}
              </div>
            </>
          )}
        </Dropdown>

        <NotificationBell />

        <button
          onClick={toggle}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-canvas hover:text-ink"
          title={`Theme: ${theme}`}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
        </button>

        <button
          onClick={() => router.push("/workspace")}
          className="flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-xs font-semibold text-white transition-colors hover:bg-brand-strong"
          title="Quick create"
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">Create</span>
        </button>

        <Dropdown
          width="w-64"
          trigger={(open) => (
            <span className={`flex h-9 items-center gap-2 rounded-lg pl-1.5 pr-2 transition-colors ${open ? "bg-canvas" : "hover:bg-canvas"}`}>
              <Avatar name={user?.full_name} src={user?.avatar_url} size="sm" />
              <span className="hidden min-w-0 text-left leading-tight sm:block">
                <span className="block max-w-28 truncate text-[13px] font-medium text-ink">{user?.full_name}</span>
                <span className="block text-[10px] text-faint">{user?.role}</span>
              </span>
            </span>
          )}
        >
          {(close) => (
            <>
              <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                <Avatar name={user?.full_name} src={user?.avatar_url} size="md" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{user?.full_name}</p>
                  <p className="truncate text-xs text-faint">{user?.email}</p>
                </div>
              </div>
              <MenuItem icon={User} label="My profile" onClick={() => { close(); router.push("/profile"); }} />
              <MenuItem icon={Settings2} label="Settings" onClick={() => { close(); router.push("/settings?tab=organization"); }} />
              <MenuItem icon={Sparkles} label="AI Companion" description="Foundation ready" onClick={() => { close(); router.push("/workspace"); }} />
              <div className="border-t border-line py-1">
                <MenuItem icon={LogOut} label="Sign out" danger onClick={() => { close(); void logout(); }} />
              </div>
            </>
          )}
        </Dropdown>
      </header>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
