"use client";

import { useEffect, useState } from "react";
import { History, RotateCcw } from "lucide-react";

import { listKnowledgeVersions, restoreKnowledgeVersion } from "@/lib/api";
import type { KnowledgeVersion } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDateTime } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export function VersionHistory({ kind, entityId }: { kind: string; entityId: string }) {
  const [versions, setVersions] = useState<KnowledgeVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<KnowledgeVersion | null>(null);
  const [restoring, setRestoring] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setVersions(await listKnowledgeVersions(kind, entityId));
    } catch {
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, entityId]);

  async function restore(version: number) {
    setRestoring(true);
    try {
      await restoreKnowledgeVersion(kind, entityId, version);
      toastSuccess(`Restored to version ${version}`);
      setSelected(null);
      await load();
    } finally {
      setRestoring(false);
    }
  }

  return (
    <Card title="Version history" subtitle="Every edit is preserved" className="mt-6">
      {loading ? (
        <div className="flex justify-center py-6"><Spinner label="Loading versions" /></div>
      ) : versions.length === 0 ? (
        <EmptyState icon={History} title="No versions yet" description="Edits will appear here." />
      ) : (
        <div className="space-y-2">
          {versions.map((version) => (
            <div key={version.id} className="flex items-start justify-between gap-3 rounded-lg border border-line px-3 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-bold text-brand">
                    v{version.version}
                  </span>
                  <p className="truncate text-[13px] font-medium text-ink">{version.title}</p>
                </div>
                <p className="mt-1 flex items-center gap-1.5 text-[12px] text-faint">
                  {version.editor_name ? (
                    <>
                      <Avatar name={version.editor_name} size="xs" /> {version.editor_name}
                    </>
                  ) : (
                    "Unknown editor"
                  )}
                  <span>·</span>
                  <span>{formatDateTime(version.created_at)}</span>
                </p>
                {version.change_note && <p className="mt-1 text-[12px] italic text-muted">“{version.change_note}”</p>}
              </div>
              <div className="flex shrink-0 gap-1.5">
                <Button size="sm" variant="ghost" onClick={() => setSelected(selected?.id === version.id ? null : version)}>
                  View
                </Button>
                <Button size="sm" variant="ghost" onClick={() => restore(version.version)} loading={restoring}>
                  <RotateCcw className="h-3.5 w-3.5" /> Restore
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div className="mt-4 rounded-lg border border-line bg-canvas p-4">
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-faint">
            Version {selected.version} — preview
          </p>
          <div className="prose-sm max-h-64 overflow-y-auto whitespace-pre-wrap text-[13px] leading-relaxed text-muted">
            {selected.content || "(empty content)"}
          </div>
        </div>
      )}
    </Card>
  );
}
