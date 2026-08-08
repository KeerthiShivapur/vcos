"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Download, Trash2, Video } from "lucide-react";

import { deleteMeetingRecording, listRecordingLibrary } from "@/lib/api";
import type { MeetingRecording } from "@/types";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge, statusTone } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { formatDateTime } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function RecordingsPage() {
  return (
    <Suspense fallback={null}>
      <RecordingsContent />
    </Suspense>
  );
}

function RecordingsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.MEETINGS_MANAGE);

  const [recordings, setRecordings] = useState<MeetingRecording[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listRecordingLibrary(statusFilter || undefined);
      setRecordings(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load recordings");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete(recording: MeetingRecording) {
    if (!window.confirm(`Delete "${recording.title}"?`)) return;
    try {
      await deleteMeetingRecording(recording.meeting_id, recording.id);
      toastSuccess("Recording deleted");
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete recording");
    }
  }

  if (error) return <ErrorState title="Could not load recordings" message={error} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recordings"
        description="Captured sessions with captions, transcripts and AI intelligence."
        actions={
          <div className="w-44">
            <Select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              placeholder="All statuses"
              options={[
                { value: "recording", label: "Recording" },
                { value: "processing", label: "Processing" },
                { value: "completed", label: "Completed" },
                { value: "failed", label: "Failed" },
              ]}
            />
          </div>
        }
      />

      {loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading recordings" />
        </div>
      ) : recordings.length === 0 ? (
        <EmptyState
          icon={Video}
          title="No recordings yet"
          description="Start a recording from a live meeting and it will show up here."
        />
      ) : (
        <div className="space-y-3">
          {recordings.map((recording) => (
            <div key={recording.id} className="card flex flex-wrap items-center gap-4 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft">
                <Video className="h-5 w-5 text-brand" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-[14px] font-semibold text-ink">{recording.title}</p>
                  <Badge tone={statusTone(recording.status)}>{recording.status}</Badge>
                  {recording.captions_enabled && <Badge tone="brand">captions</Badge>}
                </div>
                <p className="mt-0.5 text-[12px] text-faint">
                  {recording.meeting_title && (
                    <>
                      <Link href={`/meetings/${recording.meeting_id}`} className="font-medium text-brand hover:underline">
                        {recording.meeting_title}
                      </Link>
                      {" · "}
                    </>
                  )}
                  {recording.started_at ? formatDateTime(recording.started_at) : "—"}
                  {recording.duration_seconds > 0 ? ` · ${Math.round(recording.duration_seconds / 60)}m` : ""}
                  {recording.size_bytes > 0 ? ` · ${Math.max(1, Math.round(recording.size_bytes / 1048576))} MB` : ""}
                </p>
              </div>
              {recording.file_url && (
                <a
                  href={recording.file_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-secondary btn-sm"
                >
                  <Download className="h-3.5 w-3.5" /> Download
                </a>
              )}
              {canManage && (
                <Button size="sm" variant="ghost" onClick={() => void handleDelete(recording)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
