"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CheckSquare2, GitBranch, Link2, Trash2 } from "lucide-react";

import {
  addTaskDependency,
  deleteTask,
  getTask,
  listTaskDependencies,
  listTasks,
  removeTaskDependency,
  transitionTask,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Dependency, Task } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate, titleCase } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function TaskDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailContent />
    </Suspense>
  );
}

const TRANSITIONS: Record<string, string[]> = {
  backlog: ["todo", "in_progress"],
  todo: ["in_progress"],
  in_progress: ["review", "blocked", "completed"],
  review: ["in_progress", "completed"],
  blocked: ["todo", "in_progress"],
  completed: ["in_progress"],
  archived: [],
};

function DetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.TASKS_MANAGE);

  const [task, setTask] = useState<Task | null>(null);
  const [dependencies, setDependencies] = useState<Dependency[]>([]);
  const [candidates, setCandidates] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [transitioning, setTransitioning] = useState(false);
  const [savingDep, setSavingDep] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [taskData, depList, taskList] = await Promise.all([
        getTask(id),
        listTaskDependencies(id),
        listTasks({ project_id: undefined, sort: "updated" }).catch(() => [] as Task[]),
      ]);
      setTask(taskData);
      setDependencies(depList);
      setCandidates(taskList.filter((t) => t.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load task");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleTransition(status: string) {
    if (!task) return;
    setTransitioning(true);
    try {
      const updated = await transitionTask(task.id, status);
      setTask(updated);
      toastSuccess(`Moved to ${status}`);
      setLoading(true);
      try {
        const fresh = await getTask(id);
        setTask(fresh);
      } catch { /* keep local state */ }
      setLoading(false);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Transition failed");
    } finally {
      setTransitioning(false);
    }
  }

  async function handleAddDependency() {
    if (!task || !selectedCandidate) return;
    setSavingDep(true);
    try {
      await addTaskDependency(task.id, selectedCandidate);
      toastSuccess("Dependency added");
      setSelectedCandidate("");
      const fresh = await Promise.all([getTask(id), listTaskDependencies(id)]);
      setTask(fresh[0]);
      setDependencies(fresh[1]);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to add dependency");
    } finally {
      setSavingDep(false);
    }
  }

  async function handleRemoveDependency(dependencyId: string) {
    if (!task) return;
    try {
      await removeTaskDependency(task.id, dependencyId);
      toastSuccess("Dependency removed");
      const fresh = await Promise.all([getTask(id), listTaskDependencies(id)]);
      setTask(fresh[0]);
      setDependencies(fresh[1]);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to remove dependency");
    }
  }

  async function handleDelete() {
    if (!task) return;
    try {
      await deleteTask(task.id);
      toastSuccess("Task deleted");
      window.location.assign("/tasks");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete task");
    }
  }

  if (error) return <ErrorState title="Could not load task" message={error} />;
  if (loading || !task) return <div className="flex justify-center py-24"><Spinner label="Loading task" /></div>;

  const nextStates = TRANSITIONS[task.status] ?? [];
  const blocking = task.blocking_tasks ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Tasks"
        title={task.title}
        description={task.description ?? "No description"}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={statusTone(task.status)}>{task.status}</Badge>
            <Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : "neutral"}>{task.priority}</Badge>
            {canManage && task.status !== "archived" && (
              <Button size="sm" variant="danger" onClick={handleDelete}>
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Progress" subtitle={`${task.progress}% complete`}>
            <div className="h-2 overflow-hidden rounded-full bg-canvas">
              <div className="h-full rounded-full bg-brand" style={{ width: `${task.progress}%` }} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 text-[13px] sm:grid-cols-4">
              <div><p className="text-faint">Estimate</p><p className="font-medium text-ink">{task.estimate_hours ?? 0} h</p></div>
              <div><p className="text-faint">Spent</p><p className="font-medium text-ink">{task.spent_hours} h</p></div>
              <div><p className="text-faint">Started</p><p className="font-medium text-ink">{formatDate(task.start_date)}</p></div>
              <div><p className="text-faint">Due</p><p className="font-medium text-ink">{formatDate(task.due_date)}</p></div>
            </div>
          </Card>

          {canManage && nextStates.length > 0 && (
            <Card title="Transition" subtitle={`Current state: ${task.status}`}>
              <div className="flex flex-wrap gap-2">
                {nextStates.map((state) => (
                  <Button key={state} size="sm" variant={state === "completed" ? "primary" : "secondary"} loading={transitioning} onClick={() => handleTransition(state)}>
                    Mark {titleCase(state)}
                  </Button>
                ))}
              </div>
            </Card>
          )}

          <Card title="Dependencies" subtitle="What must finish before this task">
            {dependencies.length === 0 ? (
              <EmptyState icon={GitBranch} title="No dependencies" description="This task can start anytime." />
            ) : (
              <ul className="space-y-2.5">
                {dependencies.map((dep) => (
                  <li key={dep.id} className="flex items-center gap-2.5 rounded-lg bg-canvas px-3 py-2.5">
                    <Link2 className="h-4 w-4 shrink-0 text-faint" />
                    <Link href={`/tasks/${dep.depends_on_task_id}`} className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink hover:text-brand">
                      {dep.depends_on_title ?? dep.depends_on_task_id}
                    </Link>
                    <Badge>{dep.kind.replace(/_/g, " ")}</Badge>
                    {canManage && (
                      <button onClick={() => handleRemoveDependency(dep.id)} className="rounded-lg p-1 text-faint hover:bg-danger/10 hover:text-danger" title="Remove dependency">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {canManage && (
              <div className="mt-4 flex gap-2">
                <Select className="h-9 flex-1" aria-label="Depends on" options={candidates.map((c) => ({ value: c.id, label: `${c.title} (${c.status})` }))}
                  value={selectedCandidate} onChange={(e) => setSelectedCandidate(e.target.value)} placeholder="Depends on…" />
                <Button size="sm" variant="secondary" loading={savingDep} disabled={!selectedCandidate} onClick={handleAddDependency}>Add</Button>
              </div>
            )}
          </Card>

          {blocking.length > 0 && (
            <Card title="Blocked by">
              <ul className="space-y-2">
                {blocking.map((b) => (
                  <li key={b.id}>
                    <Link href={`/tasks/${b.task_id}`} className="text-[13px] font-medium text-ink hover:text-brand">
                      {b.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card title="Details">
            <dl className="space-y-3 text-[13px]">
              <DetailRow label="Project" value={task.project_name ? <Link className="text-brand hover:underline" href={`/projects/${task.project_id}`}>{task.project_name}</Link> : "—"} />
              <DetailRow label="Assignee" value={task.assignee_name ? <span className="flex items-center gap-1.5"><Avatar name={task.assignee_name} size="xs" />{task.assignee_name}</span> : "Unassigned"} />
              <DetailRow label="Reporter" value={task.reporter_name ?? "—"} />
              <DetailRow label="Epic" value={task.epic_id ? task.epic_id.slice(0, 8) : "—"} />
              <DetailRow label="Milestone" value={task.milestone_id ? task.milestone_id.slice(0, 8) : "—"} />
              <DetailRow label="Sprint" value={task.sprint_id ? task.sprint_id.slice(0, 8) : "—"} />
              <DetailRow label="Completed at" value={task.completed_at ? formatDate(task.completed_at) : "—"} />
            </dl>
          </Card>
          {task.ai_summary && (
            <Card title="AI summary">
              <p className="text-[13px] leading-relaxed text-muted">{task.ai_summary}</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-faint">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
