"use client";

import { Menu, X } from "lucide-react";

interface MobileMenuButtonProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
}

export function MobileMenuButton({ sidebarOpen, setSidebarOpen }: MobileMenuButtonProps) {
  return (
    <button
      className="fixed top-4 left-4 z-50 lg:hidden p-2 rounded-lg bg-white dark:bg-slate-800 shadow-lg border border-slate-200 dark:border-slate-700"
      onClick={() => setSidebarOpen(!sidebarOpen)}
      aria-label="Toggle menu"
    >
      {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
    </button>
  );
}