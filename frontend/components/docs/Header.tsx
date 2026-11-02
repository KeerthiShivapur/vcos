"use client";

import Link from "next/link";
import { Code, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface HeaderProps {
  activeSection: string;
  setActiveSection: (section: string) => void;
}

export function Header({ activeSection, setActiveSection }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border-b border-slate-200 dark:border-slate-800">
      <div className="max-w-5xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Embedded Analytics</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Embed VCOS analytics dashboards in your application</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setActiveSection("quick-start")}>
              <Code className="w-4 h-4 mr-2" />
              Documentation
            </Button>
            <Link href="/app/embedded-analytics" className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
              <Zap className="w-4 h-4 mr-1" />
              Try Live Demo
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}