"use client";

import {
  BookOpen,
  FileText,
  FolderTree,
  Gavel,
  ListChecks,
  Stamp,
} from "lucide-react";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  document: FileText,
  wiki: BookOpen,
  policy: Gavel,
  sop: ListChecks,
  template: Stamp,
  decision: FolderTree,
};

export function KindIcon({
  kind,
  className,
}: {
  kind: string;
  className?: string;
}) {
  const Icon = ICONS[kind] ?? FileText;
  return <Icon className={className} />;
}

export function KindIconTile({
  kind,
  className = "",
}: {
  kind: string;
  className?: string;
}) {
  return (
    <div
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand ${className}`}
    >
      <KindIcon kind={kind} className="h-5 w-5" />
    </div>
  );
}
