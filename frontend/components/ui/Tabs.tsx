"use client";

import { createContext, useContext, useState } from "react";

import { classNames } from "@/lib/utils";

interface TabsProps {
  tabs: {
    id: string;
    label: string;
    count?: number;
    icon?: React.ComponentType<{ className?: string }>;
  }[];
  active: string;
  onChange: (id: string) => void;
}

interface CompoundTabsProps {
  defaultValue: string;
  className?: string;
  children: React.ReactNode;
}

const TabsContext = createContext<{
  value: string;
  setValue: (v: string) => void;
} | null>(null);

export function Tabs(props: TabsProps | CompoundTabsProps) {
  const [internal, setInternal] = useState(
    "defaultValue" in props ? props.defaultValue : "",
  );

  if ("tabs" in props) {
    const { tabs, active, onChange } = props;
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
                  : "border-transparent text-faint hover:text-muted",
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

  return (
    <TabsContext.Provider value={{ value: internal, setValue: setInternal }}>
      <div className={props.className}>{props.children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={classNames(
        "flex flex-wrap gap-1 border-b border-line",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  className,
  children,
}: {
  value: string;
  className?: string;
  children: React.ReactNode;
}) {
  const ctx = useContext(TabsContext);
  const selected = ctx?.value === value;
  return (
    <button
      onClick={() => ctx?.setValue(value)}
      className={classNames(
        "flex items-center gap-2 border-b-2 px-3.5 py-2.5 text-[13px] font-medium transition-colors",
        selected
          ? "border-brand text-ink"
          : "border-transparent text-faint hover:text-muted",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({
  value,
  className,
  children,
}: {
  value: string;
  className?: string;
  children: React.ReactNode;
}) {
  const ctx = useContext(TabsContext);
  if (ctx?.value !== value) return null;
  return <div className={className}>{children}</div>;
}
