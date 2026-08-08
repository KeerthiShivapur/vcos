"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Gauge, ListChecks, Mic2, MonitorUp, Plus, Sparkles, Trash2, Users } from "lucide-react";

import {
  createMeetingDecision,
  deleteMeetingDecision,
  finalizeMeetingIntelligence,
  getMeetingAttendance,
  listMeetingDecisions,
} from "@/lib/api";
import type { MeetingAttendanceResponse, MeetingDecision } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import { formatDateTime } from "@/lib/utils";

interface IntelligencePanelProps {
  meetingId: string;
  canManage: boolean;
  onFinalized: () => void;
}

export function IntelligencePanel({ meetingId, canManage, onFinalized }: IntelligencePanelProps) {
  const [decisions, setDecisions] = useState<MeetingDecision[]>([]);
  const [attendance, setAttendance] = useState<MeetingAttendanceResponse | null>(null);
  const [decisionInput, setDecisionInput] = useState("");
  const [finalizing, setFinalizing] = useState(false);
  const [saving, setSaving] = useState(false);

  async function load() {
    const [decisionRows, attendanceData] = await Promise.all([
      listMeetingDecisions(meetingId).catch(() => []),
      getMeetingAttendance(meetingId).catch(() => null),
    ]);
    setDecisions(decisionRows);
    setAttendance(attendanceData);
  }

  useEffect(() => {
    void load();
  }, [meetingId]);

  async function handleFinalize() {
    setFinalizing(true);
    try {
      const result = await finalizeMeetingIntelligence(meetingId);
      const created = Array.isArray(result.action_items) ? result.action_items.length : 0;
      toastSuccess(`Meeting intelligence generated${created ? ` · ${created} tasks created` : ""}`);
      await load();
      onFinalized();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to finalize intelligence");
    } finally {
      setFinalizing(false);
    }
  }

  async function handleAddDecision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = decisionInput.trim();
    if (!content) return;
    setSaving(true);
    try {
      await createMeetingDecision(meetingId, content);
      setDecisionInput("");
      setDecisions(await listMeetingDecisions(meetingId));
      toastSuccess("Decision recorded");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to record decision");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteDecision(decisionId: string) {
    try {
      await deleteMeetingDecision(meetingId, decisionId);
      setDecisions((rows) => rows.filter((d) => d.id !== decisionId));
      toastSuccess("Decision removed");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to remove decision");
    }
  }

  const live = attendance?.live;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={attendance ? "success" : "neutral"}>
          {attendance ? `engagement ${live?.engagement_score ?? 0}/100` : "not analyzed yet"}
        </Badge>
        {canManage && (
          <Button size="sm" loading={finalizing} onClick={handleFinalize}>
            <Sparkles className="h-3.5 w-3.5" /> Generate intelligence
          </Button>
        )}
        {!canManage && <span className="text-[12px] text-faint">Ending the meeting auto-generates intelligence.</span>}
      </div>

      {attendance && live && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard icon={Gauge} label="Engagement score" value={String(live.engagement_score ?? 0)} suffix="/100" />
          <MetricCard icon={Users} label="Present" value={`${live.participants_present ?? 0}`} suffix={`/ ${live.participants_invited ?? 0} invited`} />
          <MetricCard icon={ListChecks} label="Late joiners" value={String((live.late_joiners ?? []).length)} />
          <MetricCard icon={CheckCircle2} label="Early exits" value={String((live.early_exits ?? []).length)} />
          <MetricCard icon={Mic2} label="With mic" value={String(live.with_mic ?? 0)} />
          <MetricCard icon={MonitorUp} label="Screen shares" value={String(live.screen_shares ?? 0)} />
          <MetricCard icon={ListChecks} label="Messages" value={String(live.messages_count ?? 0)} />
          <MetricCard icon={Users} label="Duration" value={formatDuration(live.duration_seconds ?? 0)} />
        </div>
      )}

      <Card title="Decisions" subtitle="Confirmed outcomes from this meeting"
        actions={canManage ? (
          <form onSubmit={handleAddDecision} className="flex items-center gap-2">
            <Input
              value={decisionInput}
              onChange={(event) => setDecisionInput(event.target.value)}
              placeholder="Record a decision…"
              className="w-64"
            />
            <Button type="submit" size="sm" loading={saving}>
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </form>
        ) : undefined}>
        {decisions.length === 0 ? (
          <EmptyState icon={ListChecks} title="No decisions yet" description="Decisions captured during the meeting appear here." />
        ) : (
          <ul className="space-y-2.5">
            {decisions.map((decision) => (
              <li key={decision.id} className="flex items-start gap-3 rounded-lg border border-line p-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] leading-relaxed text-ink">{decision.content}</p>
                  <p className="mt-0.5 text-[11px] text-faint">
                    {decision.source === "ai" ? "extracted by AI" : "recorded manually"}
                    {decision.created_at ? ` · ${formatDateTime(decision.created_at)}` : ""}
                  </p>
                </div>
                <Badge tone={decision.source === "ai" ? "brand" : "neutral"}>{decision.source}</Badge>
                {canManage && (
                  <button onClick={() => void handleDeleteDecision(decision.id)} className="rounded p-1 text-faint hover:bg-danger/10 hover:text-danger" title="Delete decision">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, suffix }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; suffix?: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-faint">
        <Icon className="h-4 w-4" />
        <p className="text-[11px] font-medium uppercase tracking-wide">{label}</p>
      </div>
      <p className="mt-1.5 text-[18px] font-semibold text-ink">
        {value}
        {suffix && <span className="ml-1 text-[12px] font-normal text-faint">{suffix}</span>}
      </p>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (!seconds) return "0m";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}
