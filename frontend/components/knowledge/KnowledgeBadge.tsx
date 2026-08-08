"use client";

import { Badge } from "@/components/ui/Badge";

export const KIND_LABELS: Record<string, string> = {
  document: "Document",
  wiki: "Wiki",
  policy: "Policy",
  sop: "SOP",
  template: "Template",
  decision: "Decision",
};

export const KIND_ICONS: Record<string, string> = {
  document: "doc",
  wiki: "wiki",
  policy: "policy",
  sop: "sop",
  template: "template",
  decision: "decision",
};

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_TONES: Record<string, "brand" | "success" | "warning" | "danger" | "neutral"> = {
  published: "success",
  approved: "success",
  made: "success",
  implemented: "success",
  reviewed: "success",
  in_review: "warning",
  proposed: "warning",
  draft: "neutral",
  archived: "neutral",
};

export function statusToneFor(status: string): "brand" | "success" | "warning" | "danger" | "neutral" {
  return STATUS_TONES[status] ?? "neutral";
}

export function KnowledgeBadge({ status, kind }: { status: string; kind?: string }) {
  return (
    <div className="flex items-center gap-2">
      {kind && <Badge tone="brand">{kindLabel(kind)}</Badge>}
      <Badge tone={statusToneFor(status)}>{status.replace(/_/g, " ")}</Badge>
    </div>
  );
}
