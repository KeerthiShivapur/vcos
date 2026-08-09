"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckSquare2, Columns3, Plus, Table2 } from "lucide-react";

import { createTask, listEmployees, listEpics, listMilestones, listProjects, listSprints, listTasks, transitionTask } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { EmployeeSummary, Epic, Milestone, Project, Sprint, Task } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { formatDate, titleCase } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function TasksPage() {
  return (
    <Suspense fallback={null}>
      <TasksContent />
    </Suspense>
  );
}

const STATUSES = ["backlog", "todo", "in_progress", "review", "blocked", "completed", "archived"];
const PRIORITIES = ["low", "medium", "high", "critical"];

function TasksContent() {
  const params = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.TASKS_MANAGE);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [epics, setEpics] = useState<Epic[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [tag, setTag] = useState(params.get("tag") ?? "");
  const [projectId, setProjectId] = useState(params.get("project_id") ?? "");
  const [assigneeId, setAssigneeId] = useState("");

  const allTags = useMemo(() => {
    const seen: string[] = [];
    tasks.forEach((t) => (t.tags ?? []).forEach((tg) => { if (!seen.includes(tg)) seen.push(tg); }));
    return seen.sort();
  }, [tasks]);

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [view, setView] = useState<"list" | "board">("list");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [taskList, projectList, empList] = await Promise.all([
        listTasks({
          project_id: projectId || undefined,
          status: status || undefined,
          priority: priority || undefined,
          tag: tag || undefined,
          assignee_id: assigneeId || undefined,
        }),
        listProjects(),
        listEmployees({ page_size: 200 }),
      ]);
      setTasks(taskList);
      setProjects(projectList);
      setEmployees(empList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load tasks");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, priority, projectId, assigneeId, tag]);

  useEffect(() => {
    if (!projectId) {
      setEpics([]);
      setMilestones([]);
      setSprints([]);
      return;
    }
    Promise.all([listEpics(projectId).catch(() => []), listMilestones(projectId).catch(() => []), listSprints(projectId).catch(() => [])]).then(
      ([e, m, s]) => {
        setEpics(e);
        setMilestones(m);
        setSprints(s);
      }
    );
  }, [projectId]);

  async function handleMove(taskId: string, direction: -1 | 1) {
    const task = tasks.find((t) => t.id === taskId);
    if (!task) return;
    const index = STATUSES.indexOf(task.status);
    const next = STATUSES[index + direction];
    if (!next) return;
    try {
      await transitionTask(taskId, next);
      toastSuccess(`${task.title} → ${titleCase(next)}`);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to move task");
    }
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFormError(null);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setFormError("Task title is required.");
      return;
    }
    setSaving(true);
    try {
      await createTask({
        project_id: String(form.get("project_id") ?? "") || undefined,
        epic_id: String(form.get("epic_id") ?? "") || undefined,
        milestone_id: String(form.get("milestone_id") ?? "") || undefined,
        sprint_id: String(form.get("sprint_id") ?? "") || undefined,
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        status: String(form.get("status") ?? "backlog"),
        priority: String(form.get("priority") ?? "medium"),
        assignee_id: String(form.get("assignee_id") ?? "") || undefined,
        estimate_hours: form.get("estimate_hours") ? Number(form.get("estimate_hours")) : undefined,
        due_date: String(form.get("due_date") ?? "") || undefined,
      });
      toastSuccess("Task created");
      setShowCreate(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create task");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        description="The task engine — assign, transition and track dependencies."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> New task
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Select className="h-9 w-44" aria-label="Project" options={projects.map((p) => ({ value: p.id, label: p.name }))}
          value={projectId} onChange={(e) => setProjectId(e.target.value)} placeholder="All projects" />
        <Select className="h-9 w-36" aria-label="Status" options={STATUSES.map((s) => ({ value: s, label: s }))}
          value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses" />
        <Select className="h-9 w-36" aria-label="Priority" options={PRIORITIES.map((p) => ({ value: p, label: p }))}
          value={priority} onChange={(e) => setPriority(e.target.value)} placeholder="All priorities" />
        <Select className="h-9 w-44" aria-label="Assignee" options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
          value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} placeholder="Anyone" />
        {allTags.length > 0 && (
          <Select className="h-9 w-36" aria-label="Label" options={allTags.map((t) => ({ value: t, label: t }))}
            value={tag} onChange={(e) => setTag(e.target.value)} placeholder="All labels" />
        )}
        <div className="ml-auto flex items-center rounded-lg border border-line bg-surface p-0.5">
          <button
            onClick={() => setView("list")}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium ${view === "list" ? "bg-brand text-white" : "text-muted hover:text-ink"}`}
          >
            <Table2 className="h-3.5 w-3.5" /> List
          </button>
          <button
            onClick={() => setView("board")}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium ${view === "board" ? "bg-brand text-white" : "text-muted hover:text-ink"}`}
          >
            <Columns3 className="h-3.5 w-3.5" /> Board
          </button>
        </div>
      </div>

      {error ? (
        <ErrorState title="Could not load tasks" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading tasks" /></div>
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={CheckSquare2}
          title="No tasks"
          description="Adjust the filters or create a task."
          action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> New task</Button> : undefined}
        />
      ) : view === "board" ? (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {STATUSES.filter((s) => s !== "archived").map((column) => {
            const columnTasks = tasks.filter((t) => t.status === column);
            const index = STATUSES.indexOf(column);
            return (
              <div key={column} className="flex min-w-60 flex-1 flex-col rounded-xl border border-line bg-surface/50">
                <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
                  <span className="text-[12px] font-semibold uppercase tracking-wide text-muted">{titleCase(column)}</span>
                  <Badge tone={column === "completed" ? "success" : column === "blocked" ? "danger" : "neutral"}>{columnTasks.length}</Badge>
                </div>
                <div className="flex flex-1 flex-col gap-2 p-2">
                  {columnTasks.map((task) => (
                    <div key={task.id} className="group rounded-lg border border-line bg-canvas p-3 transition-colors hover:border-brand/40">
                      <Link href={`/tasks/${task.id}`} className="block">
                        <p className="text-[13px] font-medium leading-snug text-ink">{task.title}</p>
                        {task.project_name && <p className="mt-0.5 truncate text-[11px] text-faint">{task.project_name}</p>}
                        {(task.tags ?? []).length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {task.tags!.map((tg) => (
                              <span key={tg} className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-medium text-brand">{tg}</span>
                            ))}
                          </div>
                        )}
                      </Link>
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : task.priority === "low" ? "neutral" : "brand"}>
                          {task.priority}
                        </Badge>
                        <div className="flex items-center gap-1">
                          {task.assignee_name ? <Avatar name={task.assignee_name} size="xs" /> : null}
                          <span className="text-[10px] text-faint">{task.due_date ? formatDate(task.due_date) : ""}</span>
                        </div>
                      </div>
                      {canManage && (
                        <div className="mt-2 flex items-center gap-1 border-t border-line pt-2">
                          <Button size="sm" variant="ghost" className="h-6 px-1.5 text-[11px]" disabled={index === 0} onClick={() => handleMove(task.id, -1)}>
                            <ArrowLeft className="h-3 w-3" /> Move
                          </Button>
                          <Button size="sm" variant="ghost" className="ml-auto h-6 px-1.5 text-[11px]" disabled={index === STATUSES.length - 2} onClick={() => handleMove(task.id, 1)}>
                            Move <ArrowRight className="h-3 w-3" />
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                  {columnTasks.length === 0 && (
                    <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-faint">
                      Empty
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Card bodyClassName="p-0">
          <Table
            head={
              <>
                <Th>Task</Th>
                <Th>Project</Th>
                <Th>Status</Th>
                <Th>Priority</Th>
                <Th>Assignee</Th>
                <Th>Due</Th>
              </>
            }
          >
            {tasks.map((task) => (
              <Tr key={task.id} onClick={() => window.location.assign(`/tasks/${task.id}`)}>
                <Td className="max-w-[260px]">
                  <p className="truncate font-medium text-ink">{task.title}</p>
                  {task.parent_task_id && <p className="text-[11px] text-faint">subtask</p>}
                  {task.description && <p className="truncate text-[12px] text-faint">{task.description}</p>}
                  {(task.tags ?? []).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {task.tags!.map((tg) => (
                        <span key={tg} className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-medium text-brand">{tg}</span>
                      ))}
                    </div>
                  )}
                </Td>
                <Td>{task.project_name ?? "—"}</Td>
                <Td><Badge tone={statusTone(task.status)}>{task.status}</Badge></Td>
                <Td>
                  <Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : task.priority === "low" ? "neutral" : "brand"}>
                    {task.priority}
                  </Badge>
                </Td>
                <Td>
                  {task.assignee_name ? (
                    <span className="flex items-center gap-1.5">
                      <Avatar name={task.assignee_name} size="sm" />
                      <span className="max-w-[120px] truncate">{task.assignee_name}</span>
                    </span>
                  ) : (
                    <span className="text-faint">Unassigned</span>
                  )}
                </Td>
                <Td className="text-muted">{formatDate(task.due_date)}</Td>
              </Tr>
            ))}
          </Table>
        </Card>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New task" description="Create a task and assign it to someone." size="lg">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Title" name="title" required placeholder="Design checkout flow" />
          <TextareaField label="Description" name="description" rows={3} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Project" name="project_id" options={projects.map((p) => ({ value: p.id, label: p.name }))} />
            <Select label="Assignee" name="assignee_id" options={employees.map((e) => ({ value: e.id, label: e.full_name }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Select label="Status" name="status" defaultValue="backlog" options={STATUSES.map((s) => ({ value: s, label: s }))} />
            <Select label="Priority" name="priority" defaultValue="medium" options={PRIORITIES.map((p) => ({ value: p, label: p }))} />
            <Input label="Estimate (h)" name="estimate_hours" type="number" min={0} step="0.5" placeholder="0" />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Select label="Epic" name="epic_id" options={epics.map((e) => ({ value: e.id, label: e.name }))} />
            <Select label="Milestone" name="milestone_id" options={milestones.map((m) => ({ value: m.id, label: m.name }))} />
            <Select label="Sprint" name="sprint_id" options={sprints.map((s) => ({ value: s.id, label: s.name }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Due date" name="due_date" type="date" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create task</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function TextareaField({ label, name, rows = 3 }: { label: string; name: string; rows?: number }) {
  return (
    <div className="w-full">
      <label className="label">{label}</label>
      <textarea name={name} rows={rows} className="input w-full resize-y" />
    </div>
  );
}
