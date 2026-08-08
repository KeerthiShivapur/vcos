"use client";

import { classNames } from "@/lib/utils";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  bodyClassName?: string;
}

export function Card({ title, subtitle, actions, className, bodyClassName, children, ...props }: CardProps) {
  return (
    <div className={classNames("card", className)} {...props}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            <h3 className="text-sm font-semibold text-ink">{title}</h3>
            {subtitle && <p className="mt-0.5 text-xs text-faint">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={classNames("p-5", bodyClassName)}>{children}</div>
    </div>
  );
}
