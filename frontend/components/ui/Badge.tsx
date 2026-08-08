"use client";

import { classNames } from "@/lib/utils";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-surface text-muted border border-line",
  brand: "bg-brand-soft text-brand",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return <span className={classNames("badge", tones[tone], className)}>{children}</span>;
}

export function statusTone(status: string): Tone {
  switch (status) {
    case "active":
    case "success":
    case "accepted":
      return "success";
    case "pending":
    case "warning":
      return "warning";
    case "suspended":
    case "deactivated":
    case "revoked":
    case "expired":
    case "failure":
    case "danger":
      return "danger";
    case "system":
    case "info":
      return "brand";
    default:
      return "neutral";
  }
}
