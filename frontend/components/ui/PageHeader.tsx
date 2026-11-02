"use client";

import { classNames } from "@/lib/utils";
import { Activity, TrendingUp, TrendingDown } from "lucide-react";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  breadcrumb?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
}: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        {breadcrumb && (
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-faint">
            {breadcrumb}
          </p>
        )}
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  trend,
  trendPositive,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  trend?: string;
  trendPositive?: boolean | null;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="card flex items-start justify-between p-4">
      <div>
        <p className="text-xs font-medium text-faint">{label}</p>
        <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">
          {value}
        </p>
        {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
        {trend && (
          <p className="mt-1 flex items-center gap-1 text-xs">
            {trendPositive === true && (
              <TrendingUp className="h-3 w-3 text-success" />
            )}
            {trendPositive === false && (
              <TrendingDown className="h-3 w-3 text-danger" />
            )}
            {trendPositive === null && (
              <Activity className="h-3 w-3 text-brand" />
            )}
            <span
              className={
                trendPositive === true
                  ? "text-success"
                  : trendPositive === false
                    ? "text-danger"
                    : "text-brand"
              }
            >
              {trend}
            </span>
          </p>
        )}
      </div>
      {Icon && (
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
          <Icon className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}
