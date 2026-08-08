"use client";

import { classNames } from "@/lib/utils";

interface TabsProps {
  tabs: { id: string; label: string; count?: number; icon?: React.ComponentType<{ className?: string }> }[];
  active: string;
  onChange: (id: string) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-line">
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={classNames(
              "flex items-center gap-2 border-b-2 px-3.5 py-2.5 text-[13px] font-medium transition-colors",
              selected
                ? "border-brand text-ink"
                : "border-transparent text-faint hover:text-muted"
            )}
          >
            {tab.icon && <tab.icon className="h-4 w-4" />}
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className="rounded-full bg-brand-soft px-1.5 py-0.5 text-[10px] font-semibold text-brand">
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
