"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bot, Lock } from "lucide-react";

import {
  cancelGovernedWorkerTask,
  createGovernedWorkerTask,
  executeGovernedWorkerAction,
  getGovernedWorkerTask,
  listGovernedWorkerTasks,
  listProjects,
  runGovernedWorkerTask,
  type GovernedWorkerTaskDetail,
  type GovernedWorkerTaskView,
} from "@/lib/api";
import { PERMISSIONS, roleCan } from "@/lib/permissions";
import type { Project } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDate, titleCase } from "@/lib/utils";

type BadgeTone = "success" | "warning" | "danger" | "neutral" | "brand";

function phaseTone(phase: string): BadgeTone {
  if (phase === "completed" || phase === "executed") return "success";
  if (phase === "awaiting_approval" || phase === "ready_to_execute")
    return "warning";
  if (
    phase === "failed" ||
    phase === "action_failed" ||
    phase === "action_rejected"
  )
    return "danger";
  if (phase === "unknown" || phase === "recovering") return "warning";
  if (phase === "running") return "brand";
  return "neutral";
}

function phaseLabel(phase: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    awaiting_approval: "Awaiting approval",
    ready_to_execute: "Ready to execute",
    executed: "Executed",
    action_rejected: "Action rejected",
    action_failed: "Action failed",
    action_cancelled: "Action cancelled",
    failed: "Failed",
    cancelled: "Cancelled",
    unknown: "Unknown",
    recovering: "Recovering",
  };
  return labels[phase] ?? titleCase(phase);
}

function ItemList({
  title,
  items,
  tone = "text-muted",
}: {
  title: string;
  items: string[];
  tone?: string;
}) {
  if (items.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">
        {title}
      </p>
      <ul className="list-disc space-y-0.5 pl-5 text-xs">
        {items.map((item, index) => (
          <li key={index} className={tone}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function GovernedAIWork() {
  const { user } = useAuth();
  const canUseAI = roleCan(user?.role, PERMISSIONS.AI_USE);

  const [tasks, setTasks] = useState<GovernedWorkerTaskView[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [instruction, setInstruction] = useState("");
  const [taskKind, setTaskKind] = useState<"research" | "recommendation">(
    "research",
  );
  const [projectId, setProjectId] = useState("");
  const [creating, setCreating] = useState(false);

  const [detail, setDetail] = useState<GovernedWorkerTaskDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const load = useCallback(async () => {
    setListError(null);
    try {
      const rows = await listGovernedWorkerTasks(50);
      setTasks(rows);
    } catch (err) {
      setTasks(null);
      setListError(err instanceof Error ? err.message : "Request failed");
    }
  }, []);

  useEffect(() => {
    if (!canUseAI) return;
    load();
    listProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, [canUseAI, load]);

  const refresh = useCallback(async () => {
    await load();
  }, [load]);

  const handleCreate = async () => {
    if (!title.trim() || !instruction.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      const created = await createGovernedWorkerTask({
        title: title.trim(),
        instruction: instruction.trim(),
        task_kind: taskKind,
        scope_type: projectId ? "project" : "company",
        scope_id: projectId || null,
      });
      const ran = await runGovernedWorkerTask(created.id);
      setTitle("");
      setInstruction("");
      await refresh();
      setDetail(ran);
      setDetailOpen(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setCreating(false);
    }
  };

  const handleRun = async (task: GovernedWorkerTaskView) => {
    setBusyId(task.id);
    setActionError(null);
    try {
      const ran = await runGovernedWorkerTask(task.id);
      await refresh();
      setDetail(ran);
      setDetailOpen(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  const handleCancel = async (task: GovernedWorkerTaskView) => {
    setBusyId(task.id);
    setActionError(null);
    try {
      await cancelGovernedWorkerTask(task.id);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusyId(null);
    }
  };

  const handleExecute = async (task: GovernedWorkerTaskView) => {
    if (!task.action_operation) return;
    setBusyId(task.id);
    setActionError(null);
    try {
      const executed = await executeGovernedWorkerAction(
        task.action_operation.id,
      );
      await refresh();
      setDetail(executed);
      setDetailOpen(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusyId(null);
    }
  };

  const handleView = async (task: GovernedWorkerTaskView) => {
    setBusyId(task.id);
    setActionError(null);
    try {
      const full = await getGovernedWorkerTask(task.id);
      setDetail(full);
      setDetailOpen(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card
      title="Governed AI Work"
      subtitle="AI tasks run as canonical operations: authorized context first, validated structured output, and no consequential action without a granted approval that is revalidated at execution time."
    >
      {!canUseAI ? (
        <div className="flex items-start gap-2 rounded-lg border border-line bg-canvas p-4 text-sm text-muted">
          <Lock className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            You do not have permission to use governed AI work. Ask an
            administrator for ai:use access.
          </p>
        </div>
      ) : (
        <div>
          <div className="grid gap-3 border-b border-line pb-4 lg:grid-cols-2">
            <Input
              label="Task title"
              id="governed-worker-title"
              placeholder="e.g. Weekly project risk briefing"
              value={title}
              maxLength={240}
              onChange={(e) => setTitle(e.target.value)}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                label="Task kind"
                id="governed-worker-kind"
                value={taskKind}
                onChange={(e) =>
                  setTaskKind(e.target.value as "research" | "recommendation")
                }
                options={[
                  { value: "research", label: "Research brief" },
                  {
                    value: "recommendation",
                    label: "Recommendation (requires approval)",
                  },
                ]}
                placeholder="Research brief"
              />
              <Select
                label="Scope"
                id="governed-worker-scope"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                options={projects.map((p) => ({ value: p.id, label: p.name }))}
                placeholder="Whole company"
              />
            </div>
            <div className="lg:col-span-2">
              <Textarea
                label="Instruction"
                id="governed-worker-instruction"
                placeholder="What should the worker investigate? Facts come only from authorized company context; the worker never invents data."
                value={instruction}
                maxLength={4000}
                rows={3}
                onChange={(e) => setInstruction(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2 lg:col-span-2">
              <Button
                onClick={handleCreate}
                disabled={creating || !title.trim() || !instruction.trim()}
              >
                {creating ? "Creating…" : "Create & run"}
              </Button>
              <Button variant="ghost" onClick={refresh}>
                Refresh
              </Button>
              <p className="text-xs text-faint">
                Recommendations create a proposed decision and a pending
                approval — never an automatic action.
              </p>
            </div>
          </div>

          {actionError && (
            <p className="mt-3 rounded-lg border border-danger/40 bg-danger/10 p-2 text-xs text-ink">
              {actionError}
            </p>
          )}

          <div className="mt-4">
            {listError ? (
              <ErrorState
                title="Could not load governed AI tasks"
                message={listError}
                onRetry={load}
              />
            ) : tasks === null ? (
              <div className="flex justify-center py-10">
                <Spinner label="Loading governed AI tasks" />
              </div>
            ) : tasks.length === 0 ? (
              <EmptyState
                icon={Bot}
                title="No governed AI tasks yet"
                description="Create a task above; every run is recorded as a canonical operation with its evidence and authorization trail."
              />
            ) : (
              <ul className="space-y-2">
                {tasks.map((task) => (
                  <li
                    key={task.id}
                    className="rounded-lg border border-line bg-surface p-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">
                          {task.title}
                        </p>
                        <p className="mt-0.5 text-xs text-faint">
                          {titleCase(task.task_kind)} ·{" "}
                          {task.scope_type === "project"
                            ? "project scope"
                            : "company scope"}
                          {" · created "}
                          {task.created_at
                            ? formatDate(task.created_at)
                            : "unknown"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {task.model?.assisted ? (
                          <Badge tone="neutral">model-assisted</Badge>
                        ) : task.state === "completed" ||
                          task.state === "failed" ? (
                          <Badge tone="neutral">facts only</Badge>
                        ) : null}
                        <Badge tone={phaseTone(task.phase)}>
                          {phaseLabel(task.phase)}
                        </Badge>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {task.phase === "queued" && (
                        <>
                          <Button
                            size="sm"
                            onClick={() => handleRun(task)}
                            disabled={busyId === task.id}
                          >
                            {busyId === task.id ? "Running…" : "Run"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCancel(task)}
                            disabled={busyId === task.id}
                          >
                            Cancel
                          </Button>
                        </>
                      )}
                      {task.phase === "ready_to_execute" &&
                        task.action_operation && (
                          <Button
                            size="sm"
                            onClick={() => handleExecute(task)}
                            disabled={busyId === task.id}
                          >
                            {busyId === task.id
                              ? "Executing…"
                              : "Execute approved action"}
                          </Button>
                        )}
                      {task.phase === "awaiting_approval" && (
                        <Link
                          href="/approvals"
                          className="text-xs text-brand hover:underline"
                        >
                          Review the pending authorization
                        </Link>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleView(task)}
                        disabled={busyId === task.id}
                      >
                        View
                      </Button>
                      {task.approval && (
                        <span className="text-xs text-faint">
                          Authorization: {task.approval.status} —{" "}
                          {task.approval.title}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <Modal
        open={detailOpen && detail !== null}
        onClose={() => setDetailOpen(false)}
        title={detail?.title ?? "Governed AI task"}
        description={
          detail
            ? `${titleCase(detail.task_kind)} · ${phaseLabel(detail.phase)} · ${
                detail.model?.assisted
                  ? `model-assisted (${detail.model.provider ?? "unknown"} / ${detail.model.model ?? "n/a"})`
                  : "facts only (model unavailable)"
              }`
            : undefined
        }
        size="lg"
      >
        {detail && (
          <div className="space-y-4 text-sm">
            {detail.error && (
              <p className="rounded-lg border border-danger/40 bg-danger/10 p-2 text-xs text-ink">
                Failure: {detail.error}
              </p>
            )}

            {detail.model && !detail.model.assisted && (
              <p className="rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs text-ink">
                No AI model was available for this run. The result below
                contains only facts retrieved from canonical company services,
                plus explicit uncertainties — no model reasoning.
              </p>
            )}

            {!detail.result && !detail.error && (
              <p className="text-xs text-muted">
                Analysis has not run yet. Use Run to execute this task.
              </p>
            )}

            {detail.result && (
              <div>
                {detail.result.summary && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">
                      Summary
                    </p>
                    <p className="text-sm text-ink">{detail.result.summary}</p>
                  </div>
                )}

                <ItemList
                  title="Observed facts (canonical services)"
                  items={detail.result.observed_facts ?? []}
                />
                <ItemList
                  title="Observed facts (model, grounded in context)"
                  items={detail.result.model_observed_facts ?? []}
                />

                {(detail.result.evidence ?? []).length > 0 && (
                  <div className="mt-3">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">
                      Evidence
                    </p>
                    <ul className="space-y-0.5 text-xs text-muted">
                      {(detail.result.evidence ?? []).map((e, index) => (
                        <li key={index}>
                          {e.claim} — {e.source}
                          {e.source_ref ? ` (${e.source_ref})` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <ItemList
                  title="Inferences (model interpretation)"
                  items={detail.result.inferences ?? []}
                />
                <ItemList
                  title="Uncertainties"
                  items={detail.result.uncertainties ?? []}
                  tone="text-warning"
                />
                <ItemList
                  title="Recommendations (proposal only)"
                  items={detail.result.recommendations ?? []}
                />

                {(detail.result.proposed_actions ?? []).length > 0 && (
                  <div className="mt-3">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">
                      Proposed actions
                    </p>
                    <ul className="space-y-1 text-xs text-muted">
                      {(detail.result.proposed_actions ?? []).map(
                        (a, index) => (
                          <li
                            key={index}
                            className="rounded-md border border-line bg-canvas px-3 py-2"
                          >
                            <span className="font-medium text-ink">
                              {a.title}
                            </span>
                            {a.description ? ` — ${a.description}` : ""}
                            {a.requires_approval ? " · requires approval" : ""}
                          </li>
                        ),
                      )}
                    </ul>
                  </div>
                )}

                {(detail.result.context_sources ?? []).length > 0 && (
                  <p className="mt-3 text-[11px] text-faint">
                    Context sources:{" "}
                    {(detail.result.context_sources ?? [])
                      .map((s) => `${s.source} (${s.status}, ${s.count})`)
                      .join(" · ")}
                  </p>
                )}
              </div>
            )}

            {detail.approval && detail.proposal_decision && (
              <div className="rounded-lg border border-line bg-canvas p-3 text-xs">
                <p className="font-semibold uppercase tracking-wide text-faint">
                  Governance
                </p>
                <p className="mt-1 text-muted">
                  Proposed decision:{" "}
                  <Link
                    href={`/decisions/${detail.proposal_decision.id}`}
                    className="text-brand hover:underline"
                  >
                    {detail.proposal_decision.title}
                  </Link>{" "}
                  ({detail.proposal_decision.status})
                </p>
                <p className="mt-1 text-muted">
                  Authorization:{" "}
                  <Link
                    href="/approvals"
                    className="text-brand hover:underline"
                  >
                    {detail.approval.title}
                  </Link>{" "}
                  ({detail.approval.status})
                </p>
              </div>
            )}

            {detail.action_result?.task_id && (
              <p className="text-xs text-muted">
                Executed action created task{" "}
                <span className="font-medium text-ink">
                  {detail.action_result.task_title}
                </span>
                {detail.action_result.executed_at
                  ? ` · ${formatDate(detail.action_result.executed_at)}`
                  : ""}
              </p>
            )}

            <p className="text-[11px] text-faint">
              {detail.completed_at
                ? `Completed ${formatDate(detail.completed_at)} · `
                : ""}
              Operation {detail.id}
            </p>
          </div>
        )}
      </Modal>
    </Card>
  );
}
