"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Eye,
  ListChecks,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  Undo2,
  Workflow,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import {
  brainKnowledgeRecommendationLifecycle,
  brainKnowledgeRecommendations,
  listProjects,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import {
  confidenceTone,
  kindLabel,
  lifecycleLabel,
  lifecycleTone,
} from "@/lib/knowledge-utils";
import type {
  KnowledgeIntelRecommendation,
  KnowledgeRecommendationLifecycleResponse,
  KnowledgeRecommendationsResponse,
  Project,
} from "@/types";

interface ActionState {
  busy: string | null;
  error: string | null;
  notice: string | null;
  note: string;
  target: "task" | "decision";
  projectId: string;
  audit: Record<string, KnowledgeRecommendationLifecycleResponse["audit"]>;
}

export default function KnowledgeWorkspaceRecommendationsPage() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.BRAIN_MANAGE);

  const [data, setData] = useState<KnowledgeRecommendationsResponse | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [actions, setActions] = useState<ActionState>({
    busy: null,
    error: null,
    notice: null,
    note: "",
    target: "task",
    projectId: "",
    audit: {},
  });

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [result, projectList] = await Promise.all([
        brainKnowledgeRecommendations({ limit: 50 }),
        listProjects({}).catch(() => []),
      ]);
      setData(result);
      setProjects(projectList);
    } catch {
      setData(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useCallback(
    async (recommendation: KnowledgeIntelRecommendation, action: string) => {
      if (!canManage || actions.busy) return;
      setActions((current) => ({
        ...current,
        busy: recommendation.id,
        error: null,
        notice: null,
      }));
      try {
        const payload: {
          action: string;
          note?: string;
          target?: string;
          project_id?: string;
        } = { action };
        if (action === "verify") {
          if (!actions.note.trim()) {
            setActions((current) => ({
              ...current,
              busy: null,
              error: "Verification needs a note",
            }));
            return;
          }
          payload.note = actions.note.trim();
        }
        if (action === "convert") {
          payload.target = actions.target;
          if (actions.target === "task" && actions.projectId) {
            payload.project_id = actions.projectId;
          }
        }
        const result = await brainKnowledgeRecommendationLifecycle(
          recommendation.id,
          payload,
        );
        setActions((current) => ({
          ...current,
          busy: null,
          notice: `${lifecycleLabel(result.lifecycle)} — ${result.task_id ? `task ${result.task_id}` : result.decision_id ? `decision ${result.decision_id}` : "updated"}`,
          note: "",
          audit: { ...current.audit, [recommendation.id]: result.audit },
        }));
        await load();
      } catch (err) {
        setActions((current) => ({
          ...current,
          busy: null,
          error: err instanceof Error ? err.message : "Action failed",
        }));
      }
    },
    [
      actions.busy,
      actions.note,
      actions.projectId,
      actions.target,
      canManage,
      load,
    ],
  );

  const sorted = useMemo(
    () =>
      (data?.recommendations ?? []).slice().sort((a, b) => {
        const order: Record<string, number> = {
          detected: 0,
          candidate: 1,
          reviewed: 2,
          accepted: 3,
          converted: 4,
          executed: 5,
          verified: 6,
        };
        return (order[a.lifecycle] ?? 9) - (order[b.lifecycle] ?? 9);
      }),
    [data],
  );

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          The knowledge layer recommends; humans execute. Every transition is
          explicit and audited — a recommendation is never converted, executed
          or resolved silently.
        </p>
        <Button size="sm" onClick={() => void load()} disabled={busy}>
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />{" "}
          Refresh
        </Button>
      </div>

      {!canManage && (
        <Card>
          <p className="text-[13px] text-muted">
            You can view recommendations. Manage access (
            <span className="font-mono">brain:manage</span>) is required to
            review, accept, convert, execute or verify them.
          </p>
        </Card>
      )}

      {actions.error && (
        <Card>
          <p className="text-[13px] text-danger">{actions.error}</p>
        </Card>
      )}
      {actions.notice && (
        <Card>
          <p className="text-[13px] text-success">{actions.notice}</p>
        </Card>
      )}

      {busy && !data ? (
        <Card>
          <div className="flex items-center justify-center py-10 text-sm text-faint">
            Materializing recommendations…
          </div>
        </Card>
      ) : !data || data.recommendations.length === 0 ? (
        <Card>
          <EmptyState
            icon={ListChecks}
            title="No active recommendations"
            description="Stale critical knowledge, unresolved conflicts, undocumented processes and cross-functional signals will surface here."
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {sorted.map((recommendation) => (
            <Card key={recommendation.id} bodyClassName="p-0">
              <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="brand">{kindLabel(recommendation.kind)}</Badge>
                    <Badge tone={lifecycleTone(recommendation.lifecycle)}>
                      {lifecycleLabel(recommendation.lifecycle)}
                    </Badge>
                    <Badge
                      tone={
                        recommendation.risk === "high"
                          ? "danger"
                          : recommendation.risk === "medium"
                            ? "warning"
                            : "success"
                      }
                    >
                      {recommendation.risk} risk
                    </Badge>
                    <Badge tone={confidenceTone(recommendation.confidence)}>
                      {(recommendation.confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <p className="mt-2 text-[13px] leading-relaxed text-ink">
                    {recommendation.reason}
                  </p>
                  <p className="mt-1.5 text-[11px] text-faint">
                    {recommendation.entities.length > 0
                      ? recommendation.entities
                          .map((entity) => entity.name ?? entity.id)
                          .join(", ")
                      : "no entity"}{" "}
                    · {recommendation.evidence.length} claims cited · updated{" "}
                    {new Date(recommendation.updated_at).toLocaleString()}
                  </p>
                </div>
              </div>

              {canManage && (
                <div className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
                  <ActionButton
                    label="Review"
                    icon={<Eye className="h-3.5 w-3.5" />}
                    shown={["detected", "candidate"].includes(
                      recommendation.lifecycle,
                    )}
                    onClick={() => void run(recommendation, "review")}
                    disabled={actions.busy !== null}
                    primary={false}
                  />
                  <ActionButton
                    label="Accept"
                    icon={<ThumbsUp className="h-3.5 w-3.5" />}
                    shown={["reviewed"].includes(recommendation.lifecycle)}
                    onClick={() => void run(recommendation, "accept")}
                    disabled={actions.busy !== null}
                    primary
                  />
                  <ActionButton
                    label="Reject"
                    icon={<ThumbsDown className="h-3.5 w-3.5" />}
                    shown={["detected", "candidate", "reviewed"].includes(
                      recommendation.lifecycle,
                    )}
                    onClick={() => void run(recommendation, "reject")}
                    disabled={actions.busy !== null}
                    primary={false}
                  />
                  <span className="flex items-center gap-1.5">
                    <select
                      value={actions.target}
                      onChange={(e) =>
                        setActions((current) => ({
                          ...current,
                          target: e.target.value as "task" | "decision",
                        }))
                      }
                      className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-brand"
                    >
                      <option value="task">Task</option>
                      <option value="decision">Decision</option>
                    </select>
                    {actions.target === "task" && (
                      <select
                        value={actions.projectId}
                        onChange={(e) =>
                          setActions((current) => ({
                            ...current,
                            projectId: e.target.value,
                          }))
                        }
                        className="max-w-[180px] rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-brand"
                      >
                        <option value="">No project</option>
                        {projects.slice(0, 50).map((project) => (
                          <option key={project.id} value={project.id}>
                            {project.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </span>
                  <ActionButton
                    label="Convert"
                    icon={<Workflow className="h-3.5 w-3.5" />}
                    shown={["accepted", "reviewed"].includes(
                      recommendation.lifecycle,
                    )}
                    onClick={() => void run(recommendation, "convert")}
                    disabled={actions.busy !== null}
                    primary={false}
                  />
                  <ActionButton
                    label="Execute"
                    icon={<Undo2 className="h-3.5 w-3.5 rotate-180" />}
                    shown={["converted", "accepted"].includes(
                      recommendation.lifecycle,
                    )}
                    onClick={() => void run(recommendation, "execute")}
                    disabled={actions.busy !== null}
                    primary={false}
                  />
                  {["converted", "executed"].includes(
                    recommendation.lifecycle,
                  ) && (
                    <span className="flex items-center gap-1.5">
                      <input
                        value={actions.note}
                        onChange={(e) =>
                          setActions((current) => ({
                            ...current,
                            note: e.target.value,
                          }))
                        }
                        placeholder="Verification note (required)"
                        className="w-56 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
                      />
                      <ActionButton
                        label="Verify"
                        icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                        shown
                        onClick={() => void run(recommendation, "verify")}
                        disabled={actions.busy !== null}
                        primary
                      />
                    </span>
                  )}
                  {actions.busy === recommendation.id && (
                    <span className="ml-auto h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
                  )}
                </div>
              )}

              {actions.audit[recommendation.id] && (
                <div className="border-t border-line px-5 py-3">
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                    Audit trail
                  </p>
                  <ol className="space-y-1">
                    {actions.audit[recommendation.id].map((event, index) => (
                      <li
                        key={index}
                        className="flex items-start gap-2 text-[11px] text-muted"
                      >
                        <Badge tone="neutral" className="shrink-0">
                          {event.action}
                        </Badge>
                        <span className="text-faint">
                          {new Date(event.at).toLocaleString()}
                          {event.note ? ` · “${event.note}”` : ""}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {data && (
        <p className="flex items-center gap-1.5 text-[11px] text-faint">
          <ChevronRight className="h-3 w-3" />
          {data.total} active · kinds: {data.active_kinds.join(", ")} ·{" "}
          {data.scope === "org" ? "org-wide view" : "scoped view"}
        </p>
      )}
    </div>
  );
}

function ActionButton({
  label,
  icon,
  shown,
  onClick,
  disabled,
  primary,
}: {
  label: string;
  icon: React.ReactNode;
  shown: boolean;
  onClick: () => void;
  disabled: boolean;
  primary: boolean;
}) {
  if (!shown) return null;
  return (
    <Button
      size="sm"
      variant={primary ? "primary" : "secondary"}
      onClick={onClick}
      disabled={disabled}
    >
      {icon} {label}
    </Button>
  );
}
