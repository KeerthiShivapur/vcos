"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckSquare2, Columns3, GripVertical, Search } from "lucide-react";

import { listEmployees, listProjects, listSprints, listTasks, transitionTask } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { EmployeeSummary, Project, Sprint, Task } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate, titleCase } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

const STATUSES = ["backlog", "todo", "in_progress", "review", "blocked", "completed"];

export default function BoardPage() {
  return (
    <Suspense fallback={null}>
      <BoardContent />
    </Suspense>
  );
}

function BoardContent() {
  const params = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.TASKS_MANAGE);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [projectId, setProjectId] = useState(params.get("project_id") ?? "");
  const [sprintId, setSprintId] = useState(params.get("sprint_id") ?? "");
  const [assigneeId, setAssigneeId] = useState("");
  const [tag, setTag] = useState("");
  const [search, setSearch] = useState("");

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);

  const allTags = useMemo(() => {
    const seen: string[] = [];
    tasks.forEach((t) => (t.tags ?? []).forEach((tg) => { if (!seen.includes(tg)) seen.push(tg); }));
    return seen.sort();
  }, [tasks]);

  const overdue = tasks.filter((t) => t.due_date && t.status !== "completed" && new Date(t.due_date) < new Date()).length;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [taskList, projectList, empList] = await Promise.all([
        listTasks({
          project_id: projectId || undefined,
          sprint_id: sprintId || undefined,
          assignee_id: assigneeId || undefined,
          tag: tag || undefined,
          search: search || undefined,
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
  }, [projectId, sprintId, assigneeId, tag, search]);

  useEffect(() => {
    if (!projectId) {
      setSprints([]);
      return;
    }
    listSprints(projectId)
      .catch(() => [] as Sprint[])
      .then((list) => {
        setSprints(list);
        setSprintId((current) => (list.some((s) => s.id === current) ? current : ""));
      });
  }, [projectId]);

  async function handleMove(taskId: string, targetStatus: string) {
    const task = tasks.find((t) => t.id === taskId);
    if (!task || task.status === targetStatus) return;
    try {
      await transitionTask(taskId, targetStatus);
      toastSuccess(`${task.title} → ${titleCase(targetStatus)}`);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to move task");
    }
  }

  function handleDragStart(event: React.DragEvent, taskId: string) {
    if (!canManage) return;
    event.dataTransfer.setData("text/plain", taskId);
    event.dataTransfer.effectAllowed = "move";
    setDraggingId(taskId);
  }

  function handleDropOnColumn(event: React.DragEvent, column: string) {
    event.preventDefault();
    const taskId = event.dataTransfer.getData("text/plain");
    setDragOver(null);
    setDraggingId(null);
    if (taskId) void handleMove(taskId, column);
  }

  const grouped = useMemo(() => {
    const map: Record<string, Task[]> = {};
    STATUSES.forEach((s) => (map[s] = []));
    tasks.forEach((t) => {
      if (map[t.status]) map[t.status].push(t);
    });
    return map;
  }, [tasks]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Work board"
        description="Drag tasks across the board — transitions respect dependencies and roll progress up."
        actions={
          canManage ? (
            <Button size="sm" variant="secondary" onClick={() => window.location.assign("/tasks")}>
              <Columns3 className="h-4 w-4" /> Open tasks
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Select className="h-9 w-44" aria-label="Project" options={projects.map((p) => ({ value: p.id, label: p.name }))}
          value={projectId} onChange={(e) => setProjectId(e.target.value)} placeholder="All projects" />
        {projectId && (
          <Select className="h-9 w-44" aria-label="Sprint" options={sprints.map((s) => ({ value: s.id, label: s.name }))}
            value={sprintId} onChange={(e) => setSprintId(e.target.value)} placeholder="All sprints" />
        )}
        <Select className="h-9 w-44" aria-label="Assignee" options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
          value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} placeholder="Anyone" />
        {allTags.length > 0 && (
          <Select className="h-9 w-36" aria-label="Label" options={allTags.map((t) => ({ value: t, label: t }))}
            value={tag} onChange={(e) => setTag(e.target.value)} placeholder="All labels" />
        )}
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
          <Input
            className="h-9 w-52 pl-8"
            aria-label="Search tasks"
            placeholder="Search tasks…"
            defaultValue={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="ml-auto flex items-center gap-2 text-[12px] text-faint">
          <Badge tone="neutral">{tasks.length} tasks</Badge>
          {overdue > 0 && <Badge tone="danger">{overdue} overdue</Badge>}
        </div>
      </div>

      {error ? (
        <ErrorState title="Could not load the board" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading board" /></div>
      ) : (
        <div className="flex items-start gap-4 overflow-x-auto pb-2">
          {STATUSES.map((column) => {
            const columnTasks = grouped[column];
            return (
              <div
                key={column}
                data-status={column}
                onDragOver={(e) => { if (canManage) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setDragOver(column); } }}
                onDragLeave={() => setDragOver((current) => (current === column ? null : current))}
                onDrop={(e) => handleDropOnColumn(e, column)}
                className={`flex min-h-[420px] min-w-64 flex-1 flex-col rounded-xl border bg-surface/50 transition-colors ${
                  dragOver === column ? "border-brand bg-brand/5" : "border-line"
                }`}
              >
                <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
                  <span className="text-[12px] font-semibold uppercase tracking-wide text-muted">{titleCase(column)}</span>
                  <Badge tone={column === "completed" ? "success" : column === "blocked" ? "danger" : "neutral"}>{columnTasks.length}</Badge>
                </div>
                <div className="flex flex-1 flex-col gap-2 p-2">
                  {columnTasks.map((task) => (
                    <div
                      key={task.id}
                      data-task-id={task.id}
                      draggable={canManage}
                      onDragStart={(e) => handleDragStart(e, task.id)}
                      onDragEnd={() => { setDraggingId(null); setDragOver(null); }}
                      className={`group cursor-grab rounded-lg border bg-canvas p-3 transition-all hover:border-brand/40 active:cursor-grabbing ${
                        draggingId === task.id ? "opacity-50 ring-2 ring-brand/40" : "border-line"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <Link href={`/tasks/${task.id}`} className="min-w-0 flex-1">
                          <p className="text-[13px] font-medium leading-snug text-ink">{task.title}</p>
                          {task.project_name && <p className="mt-0.5 truncate text-[11px] text-faint">{task.project_name}</p>}
                        </Link>
                        {canManage && <GripVertical className="mt-0.5 h-3.5 w-3.5 shrink-0 text-faint" />}
                      </div>
                      {(task.tags ?? []).length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {task.tags!.map((tg) => (
                            <span key={tg} className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-medium text-brand">{tg}</span>
                          ))}
                        </div>
                      )}
                      <div className="mt-1.5 flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-1.5">
                          <Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : task.priority === "low" ? "neutral" : "brand"}>
                            {task.priority}
                          </Badge>
                          {(task.blocked_by ?? []).length > 0 && (
                            <span title={(task.blocked_by ?? []).map((b) => b.title).join(", ")} className="rounded-full bg-danger/10 px-2 py-0.5 text-[10px] font-medium text-danger">
                              {task.blocked_by!.length} blocker{task.blocked_by!.length > 1 ? "s" : ""}
                            </span>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          {task.assignee_name ? <Avatar name={task.assignee_name} size="xs" /> : null}
                          <span className="text-[10px] text-faint">{task.due_date ? formatDate(task.due_date) : ""}</span>
                        </div>
                      </div>
                      {task.status === "in_progress" && task.progress > 0 && (
                        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-line">
                          <div className="h-full rounded-full bg-brand" style={{ width: `${task.progress}%` }} />
                        </div>
                      )}
                    </div>
                  ))}
                  {columnTasks.length === 0 && (
                    <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-faint">
                      {canManage ? "Drop tasks here" : "Empty"}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && !error && tasks.length === 0 && (
        <EmptyState
          icon={CheckSquare2}
          title="No tasks match the filters"
          description="Adjust the filters above or create a task to start executing."
          action={canManage ? <Button size="sm" onClick={() => window.location.assign("/tasks")}>New task</Button> : undefined}
        />
      )}
    </div>
  );
}
