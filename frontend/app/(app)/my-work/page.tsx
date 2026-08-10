"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CalendarClock, CheckCircle2, Gauge, ListTodo, Target } from "lucide-react";

import { getMyWork, listTasks, transitionTask } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { MyWork, Task } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, statusTone } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function MyWorkPage() {
  return (
    <Suspense fallback={null}>
      <MyWorkContent />
    </Suspense>
  );
}

function MyWorkContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.TASKS_MANAGE);

  const [data, setData] = useState<MyWork | null>(null);
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [myWork, taskList] = await Promise.all([getMyWork(), listTasks({})]);
      setData(myWork);
      setAllTasks(taskList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load your work");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function quickTransition(taskId: string, status: string) {
    try {
      await transitionTask(taskId, status);
      toastSuccess(`Task moved to ${status}`);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to update task");
    }
  }

  if (error) return <ErrorState title="Could not load your work" message={error} />;
  if (loading || !data) return <div className="flex justify-center py-24"><Spinner label="Loading your work" /></div>;

  const wl = data.workload;
  const overloaded = wl.is_overloaded;

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Work"
        description="Everything on your plate — tasks, meetings, goals and capacity."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Open tasks" value={data.tasks.total} hint={`${data.tasks.in_progress} in progress`} icon={ListTodo} />
        <StatCard label="Overdue" value={data.tasks.overdue} hint="Needs attention" icon={AlertTriangle} />
        <StatCard label="Upcoming meetings" value={data.upcoming_meetings} hint="Scheduled ahead" icon={CalendarClock} />
        <StatCard label="Owned goals" value={data.goals.length} hint="You are the owner" icon={Target} />
      </div>

      <div className={`card p-5 ${overloaded ? "border-danger/40" : ""}`}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">Weekly capacity</p>
            <p className="text-[12px] text-faint">
              {wl.allocated_hours}h tasks + {wl.meeting_hours}h meetings of {wl.capacity_hours}h — {wl.utilization}% utilized
            </p>
          </div>
          <Badge tone={overloaded ? "danger" : wl.utilization > 70 ? "warning" : "success"}>
            {overloaded ? "Overloaded" : wl.utilization > 70 ? "Heavy" : "Balanced"}
          </Badge>
        </div>
        <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-canvas">
          <div className={`h-full rounded-full ${overloaded ? "bg-danger" : "bg-brand"}`} style={{ width: `${Math.min(100, wl.utilization)}%` }} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Today's tasks" subtitle="Priority by due date">
            {data.today_tasks.length === 0 ? (
              <EmptyState icon={ListTodo} title="All clear" description="No open tasks assigned to you." />
            ) : (
              <ul className="divide-y divide-line">
                {data.today_tasks.map((task) => {
                  const full = allTasks.find((t) => t.id === task.id);
                  const isOverdue = task.due_date && new Date(task.due_date) < new Date();
                  return (
                    <li key={task.id} className="flex items-center gap-3 py-3">
                      <Link href={`/tasks/${task.id}`} className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-ink hover:text-brand">{task.title}</p>
                        <p className="text-[12px] text-faint">
                          {full?.project_name ?? "No project"}
                          {full?.decision ? ` · from decision "${full.decision.title}"` : ""}
                          {task.due_date ? ` · due ${formatDate(task.due_date)}` : ""}
                        </p>
                      </Link>
                      {isOverdue && task.status !== "completed" && <Badge tone="danger">overdue</Badge>}
                      <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                      {canManage && task.status !== "completed" && (
                        <Button size="sm" variant="ghost" onClick={() => quickTransition(task.id, "completed")}>
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="My goals" subtitle="Objectives you own">
            {data.goals.length === 0 ? (
              <EmptyState icon={Target} title="No owned goals" />
            ) : (
              <ul className="space-y-3">
                {data.goals.map((goal) => (
                  <li key={goal.id}>
                    <Link href={`/goals/${goal.id}`} className="block rounded-lg border border-line p-3 transition-colors hover:bg-canvas/60">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-[13px] font-medium text-ink">{goal.name}</p>
                        <Badge tone={statusTone(goal.status)}>{goal.status}</Badge>
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-canvas">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.round(goal.progress)}%` }} />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Capacity">
            <div className="flex items-center gap-2.5">
              <Gauge className="h-4 w-4 text-faint" />
              <p className="text-[13px] text-muted">
                {wl.active_tasks} active task{wl.active_tasks === 1 ? "" : "s"} · {wl.allocated_hours}h allocated
              </p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
