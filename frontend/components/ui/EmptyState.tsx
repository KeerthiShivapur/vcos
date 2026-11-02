"use client";

import { Inbox } from "lucide-react";

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-canvas text-faint">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="mt-1 text-sm font-semibold text-ink">{title}</h3>
      {description && (
        <p className="max-w-sm text-[13px] text-faint">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
