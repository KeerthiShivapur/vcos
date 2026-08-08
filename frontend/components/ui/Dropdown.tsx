"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { classNames } from "@/lib/utils";

interface DropdownProps {
  trigger: (open: boolean) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "left" | "right";
  width?: string;
  className?: string;
}

export function Dropdown({ trigger, children, align = "right", width = "w-64", className }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  return (
    <div ref={ref} className={classNames("relative", className)}>
      <div onClick={() => setOpen((v) => !v)} className="cursor-pointer">
        {trigger(open)}
      </div>
      {open && (
        <div
          className={classNames(
            "absolute z-50 mt-2 animate-pop overflow-hidden rounded-xl border border-line bg-elevated shadow-popover",
            align === "right" ? "right-0" : "left-0",
            width
          )}
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}

export function MenuItem({
  icon: Icon,
  label,
  onClick,
  danger,
  description,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  label: string;
  onClick?: () => void;
  danger?: boolean;
  description?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={classNames(
        "flex w-full items-center gap-3 px-3.5 py-2.5 text-left text-sm transition-colors hover:bg-canvas",
        danger ? "text-danger" : "text-ink"
      )}
    >
      {Icon && <Icon className="h-4 w-4 shrink-0 text-faint" />}
      <span className="min-w-0">
        <span className="block truncate font-medium">{label}</span>
        {description && <span className="block truncate text-xs text-faint">{description}</span>}
      </span>
    </button>
  );
}
