"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  CheckCircle2,
  CheckSquare2,
  ClipboardList,
  FileText,
  GitBranch,
  Link2,
  MessageSquare,
  Paperclip,
  Plus,
  RefreshCcw,
  Stamp,
  Trash2,
} from "lucide-react";

import {
  addTaskAttachment,
  addTaskComment,
  addTaskDependency,
  createApproval,
  createTask,
  deleteTask,
  deleteTaskAttachment,
  deleteTaskComment,
  getMyEmployee,
  getTask,
  getTaskActivity,
  listEmployees,
  listTaskAttachments,
  listTaskComments,
  listTaskDependencies,
  listTasks,
  removeTaskDependency,
  transitionTask,
  updateTask,
} from "@/lib/api";
import type { EmployeeSummary, Task, TaskActivityEntry, TaskAttachment, TaskComment } from "@/types";
import { PERMISSIONS, roleCan } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate, formatDateTime, titleCase } from "@/lib/utils";
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

const PRIORITIES = ["low", "medium", "high", "critical"];

function DetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.TASKS_MANAGE);

  const [task, setTask] = useState<Task | null>(null);
  const [me, setMe] = useState<{ id: string } | null>(null);
  const [dependencies, setDependencies] = useState<{ id: string; depends_on_task_id: string; depends_on_title: string | null; kind: string }[]>([]);
  const [candidates, setCandidates] = useState<Task[]>([]);
  const [subtasks, setSubtasks] = useState<Task[]>([]);
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [attachments, setAttachments] = useState<TaskAttachment[]>([]);
  const [activity, setActivity] = useState<TaskActivityEntry[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", priority: "medium", due_date: "", assignee_id: "", tags: "" });
  const [transitioning, setTransitioning] = useState(false);

  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [approvalForm, setApprovalForm] = useState({
    approval_type: "task",
    title: "",
    description: "",
    approver_id: "",
    priority: "medium",
    due_at: "",
  });

  const [commentBody, setCommentBody] = useState("");
  const [sendingComment, setSendingComment] = useState(false);

  const [subTitle, setSubTitle] = useState("");
  const [addingSub, setAddingSub] = useState(false);

  const [attachName, setAttachName] = useState("");
  const [attachUrl, setAttachUrl] = useState("");
  const [addingAttach, setAddingAttach] = useState(false);

  const [savingDep, setSavingDep] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [taskData, depList, taskList, subList, commentList, attachList, actList, empList, meData] =
        await Promise.all([
          getTask(id),
          listTaskDependencies(id),
          listTasks({ sort: "updated" }).catch(() => [] as Task[]),
          listTasks({ parent_task_id: id }).catch(() => [] as Task[]),
          listTaskComments(id),
          listTaskAttachments(id),
          getTaskActivity(id),
          listEmployees({ page_size: 200 }).catch(() => [] as EmployeeSummary[]),
          getMyEmployee().catch(() => null),
        ]);
      setTask(taskData);
      setDependencies(depList);
      setCandidates(taskList.filter((t) => t.id !== id && t.parent_task_id !== id));
      setSubtasks(subList);
      setComments(commentList);
      setAttachments(attachList);
      setActivity(actList);
      setEmployees(empList);
      setMe(meData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load task");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const isAssignee = me !== null && task !== null && task.assignee_id === me.id;
  const canEdit = canManage || isAssignee;

  function openEdit() {
    if (!task) return;
    setForm({
      title: task.title,
      description: task.description ?? "",
      priority: task.priority,
      due_date: task.due_date ? String(task.due_date).slice(0, 10) : "",
      assignee_id: task.assignee_id ?? "",
      tags: (task.tags ?? []).join(", "),
    });
    setEditOpen(true);
  }

  function openApproval() {
    if (!task) return;
    setApprovalForm({
      approval_type: "task",
      title: `Approve: ${task.title}`,
      description: "",
      approver_id: "",
      priority: "medium",
      due_at: "",
    });
    setApprovalOpen(true);
  }

  async function handleRequestApproval() {
    if (!task) return;
    if (!approvalForm.title.trim()) return toastError("Title is required");
    if (!approvalForm.approver_id) return toastError("Choose an approver");
    setApprovalBusy(true);
    try {
      const payload: Record<string, unknown> = {
        approval_type: approvalForm.approval_type,
        title: approvalForm.title.trim(),
        description: approvalForm.description.trim() || undefined,
        approver_id: approvalForm.approver_id,
        priority: approvalForm.priority,
        entity_type: "task",
        entity_id: task.id,
      };
      if (approvalForm.due_at) payload.due_at = new Date(`${approvalForm.due_at}T00:00:00`).toISOString();
      await createApproval(payload);
      toastSuccess("Approval requested — the approver has been notified");
      setApprovalOpen(false);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to request approval");
    } finally {
      setApprovalBusy(false);
    }
  }

  async function handleSaveEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!task) return;
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        priority: form.priority,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      };
      if (form.due_date) payload.due_date = form.due_date;
      else payload.due_date = null;
      if (canManage) payload.assignee_id = form.assignee_id || null;
      const updated = await updateTask(task.id, payload);
      setTask(updated);
      toastSuccess("Task updated");
      setEditOpen(false);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to save task");
    } finally {
      setSaving(false);
    }
  }

  async function handleTransition(status: string) {
    if (!task) return;
    setTransitioning(true);
    try {
      const updated = await transitionTask(task.id, status);
      setTask(updated);
      toastSuccess(`Moved to ${status}`);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Transition failed");
    } finally {
      setTransitioning(false);
    }
  }

  async function handleComment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!task || !commentBody.trim()) return;
    setSendingComment(true);
    try {
      await addTaskComment(task.id, commentBody.trim());
      setCommentBody("");
      toastSuccess("Comment added");
      setComments(await listTaskComments(task.id));
      setActivity(await getTaskActivity(task.id));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to comment");
    } finally {
      setSendingComment(false);
    }
  }

  async function handleDeleteComment(commentId: string) {
    if (!task) return;
    try {
      await deleteTaskComment(task.id, commentId);
      toastSuccess("Comment deleted");
      setComments(await listTaskComments(task.id));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete comment");
    }
  }

  async function handleAddSubtask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!task || !subTitle.trim()) return;
    setAddingSub(true);
    try {
      await createTask({
        title: subTitle.trim(),
        parent_task_id: task.id,
        project_id: task.project_id ?? undefined,
        assignee_id: task.assignee_id ?? undefined,
        status: "todo",
      });
      setSubTitle("");
      toastSuccess("Subtask added");
      setSubtasks(await listTasks({ parent_task_id: task.id }));
      setTask(await getTask(task.id));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to add subtask");
    } finally {
      setAddingSub(false);
    }
  }

  async function handleSubtaskTransition(subtask: Task, status: string) {
    try {
      await transitionTask(subtask.id, status);
      toastSuccess(`${subtask.title} → ${titleCase(status)}`);
      setSubtasks(await listTasks({ parent_task_id: task?.id ?? "" }));
      setTask(await getTask(task?.id ?? ""));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to update subtask");
    }
  }

  async function handleAddAttachment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!task || !attachName.trim() || !attachUrl.trim()) return;
    setAddingAttach(true);
    try {
      await addTaskAttachment(task.id, { filename: attachName.trim(), url: attachUrl.trim() });
      setAttachName("");
      setAttachUrl("");
      toastSuccess("Attachment added");
      setAttachments(await listTaskAttachments(task.id));
      setActivity(await getTaskActivity(task.id));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to add attachment");
    } finally {
      setAddingAttach(false);
    }
  }

  async function handleDeleteAttachment(attachmentId: string) {
    if (!task) return;
    try {
      await deleteTaskAttachment(task.id, attachmentId);
      toastSuccess("Attachment removed");
      setAttachments(await listTaskAttachments(task.id));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to remove attachment");
    }
  }

  async function handleAddDependency() {
    if (!task || !selectedCandidate) return;
    setSavingDep(true);
    try {
      await addTaskDependency(task.id, selectedCandidate);
      toastSuccess("Dependency added");
      setSelectedCandidate("");
      setDependencies(await listTaskDependencies(task.id));
      setTask(await getTask(task.id));
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
      setDependencies(await listTaskDependencies(task.id));
      setTask(await getTask(task.id));
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

  const blockers = useMemo(() => task?.blocked_by ?? [], [task]);

  if (error) return <ErrorState title="Could not load task" message={error} />;
  if (loading || !task) return <div className="flex justify-center py-24"><Spinner label="Loading task" /></div>;

  const nextStates = TRANSITIONS[task.status] ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={task.parent_task_id ? "Tasks · Subtask" : "Tasks"}
        title={task.title}
        description={task.description ?? "No description"}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={statusTone(task.status)}>{task.status}</Badge>
            <Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : "neutral"}>{task.priority}</Badge>
            {task.parent_task_id && (
              <Link href={`/tasks/${task.parent_task_id}`}>
                <Badge tone="brand">↳ parent</Badge>
              </Link>
            )}
            {canEdit && task.status !== "archived" && (
              <Button size="sm" variant="secondary" onClick={openEdit}>
                <ClipboardList className="h-4 w-4" /> Edit
              </Button>
            )}
            {roleCan(user?.role, PERMISSIONS.APPROVALS_MANAGE) && task.status !== "archived" && (
              <Button size="sm" variant="secondary" onClick={openApproval}>
                <Stamp className="h-4 w-4" /> Request approval
              </Button>
            )}
            {canManage && task.status !== "archived" && (
              <Button size="sm" variant="danger" onClick={handleDelete}>
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        }
      />

      {blockers.length > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3">
          <GitBranch className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
          <div className="text-[13px] text-danger">
            <p className="font-semibold">This task cannot proceed — blocked by:</p>
            <ul className="mt-1 space-y-0.5">
              {blockers.map((b) => (
                <li key={b.id}>
                  <Link href={`/tasks/${b.task_id}`} className="underline underline-offset-2">
                    {b.title}
                  </Link>{" "}
                  <span className="text-danger/70">({b.status.replace(/_/g, " ")})</span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-danger/70">Finish or remove the blocker, and this task unlocks automatically.</p>
          </div>
        </div>
      )}

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

          {canEdit && nextStates.length > 0 && (
            <Card title="Execute" subtitle={`Current state: ${task.status} — move the work forward`}>
              <div className="flex flex-wrap gap-2">
                {nextStates.map((state) => (
                  <Button key={state} size="sm" variant={state === "completed" ? "primary" : "secondary"} loading={transitioning} onClick={() => handleTransition(state)}>
                    {state === "completed" ? <CheckCircle2 className="h-4 w-4" /> : null}
                    Mark {titleCase(state)}
                  </Button>
                ))}
              </div>
            </Card>
          )}

          <Card title="Subtasks" subtitle={subtasks.length > 0 ? `${task.subtasks_completed}/${subtasks.length} complete` : "Break this task into smaller pieces"}>
            {subtasks.length === 0 ? (
              <EmptyState icon={CheckSquare2} title="No subtasks yet" description="Subtasks track the real work inside a larger task." />
            ) : (
              <ul className="space-y-2">
                {subtasks.map((sub) => (
                  <li key={sub.id} className="flex items-center gap-2.5 rounded-lg bg-canvas px-3 py-2.5">
                    <button
                      onClick={() => handleSubtaskTransition(sub, sub.status === "completed" ? "in_progress" : "completed")}
                      disabled={!canEdit && !canManage}
                      title="Toggle done"
                      className="shrink-0 text-faint hover:text-brand disabled:opacity-40"
                    >
                      {sub.status === "completed" ? <CheckCircle2 className="h-4 w-4 text-brand" /> : <CheckSquare2 className="h-4 w-4" />}
                    </button>
                    <Link href={`/tasks/${sub.id}`} className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink hover:text-brand">
                      {sub.title}
                    </Link>
                    <Badge tone={statusTone(sub.status)}>{sub.status}</Badge>
                  </li>
                ))}
              </ul>
            )}
            {canEdit && (
              <form onSubmit={handleAddSubtask} className="mt-4 flex gap-2">
                <Input className="h-9 flex-1" placeholder="New subtask…" value={subTitle} onChange={(e) => setSubTitle(e.target.value)} />
                <Button size="sm" variant="secondary" type="submit" loading={addingSub} disabled={!subTitle.trim()}>
                  <Plus className="h-4 w-4" /> Add
                </Button>
              </form>
            )}
          </Card>

          <Card title="Comments" subtitle="Discuss the work — @mention colleagues by email">
            {comments.length === 0 ? (
              <EmptyState icon={MessageSquare} title="No comments yet" />
            ) : (
              <ul className="space-y-3">
                {comments.map((c) => (
                  <li key={c.id} className="rounded-lg bg-canvas px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      {c.author_name ? <Avatar name={c.author_name} size="xs" /> : null}
                      <span className="text-[12px] font-semibold text-ink">{c.author_name ?? "Someone"}</span>
                      <span className="text-[11px] text-faint">{formatDateTime(c.created_at)}</span>
                      {(canManage || (me !== null && c.author_id === me.id)) && (
                        <button onClick={() => handleDeleteComment(c.id)} className="ml-auto rounded p-1 text-faint hover:bg-danger/10 hover:text-danger" title="Delete comment">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-[13px] text-muted">{c.body}</p>
                  </li>
                ))}
              </ul>
            )}
            {canEdit && (
              <form onSubmit={handleComment} className="mt-4 flex gap-2">
                <Input className="h-9 flex-1" placeholder="Write a comment… (e.g. @ada@acme.test.co)" value={commentBody} onChange={(e) => setCommentBody(e.target.value)} />
                <Button size="sm" variant="secondary" type="submit" loading={sendingComment} disabled={!commentBody.trim()}>
                  Comment
                </Button>
              </form>
            )}
          </Card>

          <Card title="Attachments" subtitle="Link the material the work depends on">
            {attachments.length === 0 ? (
              <EmptyState icon={Paperclip} title="No attachments" />
            ) : (
              <ul className="space-y-2">
                {attachments.map((a) => (
                  <li key={a.id} className="flex items-center gap-2.5 rounded-lg bg-canvas px-3 py-2.5">
                    <FileText className="h-4 w-4 shrink-0 text-faint" />
                    <a href={a.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink hover:text-brand">
                      {a.filename}
                    </a>
                    {a.uploaded_by_name && <span className="text-[11px] text-faint">{a.uploaded_by_name}</span>}
                    {(canManage || (me !== null && a.uploaded_by === me.id)) && (
                      <button onClick={() => handleDeleteAttachment(a.id)} className="rounded p-1 text-faint hover:bg-danger/10 hover:text-danger" title="Remove attachment">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {canEdit && (
              <form onSubmit={handleAddAttachment} className="mt-4 flex flex-wrap gap-2">
                <Input className="h-9 flex-1" placeholder="File name (e.g. spec.pdf)" value={attachName} onChange={(e) => setAttachName(e.target.value)} />
                <Input className="h-9 flex-1" placeholder="https://…" value={attachUrl} onChange={(e) => setAttachUrl(e.target.value)} />
                <Button size="sm" variant="secondary" type="submit" loading={addingAttach} disabled={!attachName.trim() || !attachUrl.trim()}>
                  <Paperclip className="h-4 w-4" /> Attach
                </Button>
              </form>
            )}
          </Card>

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
        </div>

        <div className="space-y-6">
          <Card title="Details">
            <dl className="space-y-3 text-[13px]">
              <DetailRow label="Project" value={task.project_name ? <Link className="text-brand hover:underline" href={`/projects/${task.project_id}`}>{task.project_name}</Link> : "—"} />
              <DetailRow label="Assignee" value={task.assignee_name ? <span className="flex items-center gap-1.5"><Avatar name={task.assignee_name} size="xs" />{task.assignee_name}{isAssignee ? " (you)" : ""}</span> : "Unassigned"} />
              <DetailRow label="Reporter" value={task.reporter_name ?? "—"} />
              <DetailRow label="Due" value={formatDate(task.due_date)} />
              <DetailRow label="Completed at" value={task.completed_at ? formatDate(task.completed_at) : "—"} />
            </dl>
          </Card>

          {(task.tags ?? []).length > 0 && (
            <Card title="Labels">
              <div className="flex flex-wrap gap-1.5">
                {task.tags!.map((tag) => (
                  <span key={tag} className="rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-medium text-brand">{tag}</span>
                ))}
              </div>
            </Card>
          )}

          {activity.length > 0 && (
            <Card title="Activity" subtitle="The full execution history">
              <ol className="space-y-3">
                {activity.map((a) => (
                  <li key={a.id} className="relative pl-4">
                    <span className="absolute left-0 top-1.5 h-1.5 w-1.5 rounded-full bg-brand/60" />
                    <p className="text-[12px] font-medium text-ink">{activityLabel(a.action)}</p>
                    <p className="text-[11px] text-faint">
                      {a.actor_email ?? "system"} · {formatDateTime(a.created_at)}
                    </p>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {task.ai_summary && (
            <Card title="AI summary">
              <p className="text-[13px] leading-relaxed text-muted">{task.ai_summary}</p>
            </Card>
          )}
        </div>
      </div>

      {approvalOpen && task && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onClick={() => setApprovalOpen(false)}>
          <div role="dialog" aria-modal="true" className="w-full max-w-lg rounded-2xl border border-line bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-[15px] font-semibold text-ink">Request approval</h3>
            <p className="mt-0.5 text-[12px] text-faint">The approver is notified instantly and decides from the Approvals queue.</p>
            <div className="mt-4 space-y-4">
              <Select
                label="Type"
                aria-label="Approval type"
                value={approvalForm.approval_type}
                onChange={(event) => setApprovalForm({ ...approvalForm, approval_type: event.target.value })}
                options={["task", "release", "budget", "project", "purchase", "document", "other"].map((t) => ({ value: t, label: t }))}
              />
              <Input label="Title" name="approval-title" value={approvalForm.title} onChange={(e) => setApprovalForm({ ...approvalForm, title: e.target.value })} required />
              <div className="w-full">
                <label htmlFor="approval-description" className="label">Context for the approver</label>
                <textarea id="approval-description" rows={3} className="input w-full resize-y" value={approvalForm.description} onChange={(e) => setApprovalForm({ ...approvalForm, description: e.target.value })} />
              </div>
              <Select
                label="Approver"
                aria-label="Approver"
                value={approvalForm.approver_id}
                onChange={(event) => setApprovalForm({ ...approvalForm, approver_id: event.target.value })}
                options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
                placeholder="Choose who decides"
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">Priority</label>
                  <Select
                    aria-label="Priority"
                    value={approvalForm.priority}
                    onChange={(event) => setApprovalForm({ ...approvalForm, priority: event.target.value })}
                    options={["low", "medium", "high", "critical"].map((p) => ({ value: p, label: p }))}
                  />
                </div>
                <Input label="Due by" name="approval-due" type="date" value={approvalForm.due_at} onChange={(e) => setApprovalForm({ ...approvalForm, due_at: e.target.value })} />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button type="button" variant="ghost" onClick={() => setApprovalOpen(false)}>Cancel</Button>
                <Button type="button" onClick={handleRequestApproval} loading={approvalBusy}>Request approval</Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {editOpen && task && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onClick={() => setEditOpen(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-line bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-[15px] font-semibold text-ink">Edit task</h3>
            <p className="mt-0.5 text-[12px] text-faint">Changes are recorded in the activity history.</p>
            <form onSubmit={handleSaveEdit} className="mt-4 space-y-4">
              <Input label="Title" name="edit-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
              <div className="w-full">
                <label htmlFor="edit-description" className="label">Description</label>
                <textarea id="edit-description" rows={4} className="input w-full resize-y" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">Priority</label>
                  <Select aria-label="Priority" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} options={PRIORITIES.map((p) => ({ value: p, label: p }))} />
                </div>
                <Input label="Due date" name="edit-due" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
              </div>
              {canManage && (
                <div>
                  <label className="label">Assignee</label>
                  <Select aria-label="Assignee" value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })}
                    options={employees.map((e) => ({ value: e.id, label: e.full_name }))} placeholder="Unassigned" />
                </div>
              )}
              <Input label="Labels (comma separated)" name="edit-labels" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="urgent, sales" />
              <div className="flex justify-end gap-2 pt-1">
                <Button type="button" variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
                <Button type="submit" loading={saving}>Save changes</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function activityLabel(action: string): string {
  const map: Record<string, string> = {
    "task.created": "Task created",
    "task.updated": "Task updated",
    "task.transitioned": "Status changed",
    "task.completed": "Task completed",
    "task.deleted": "Task deleted",
    "task.commented": "Comment added",
    "task.comment_deleted": "Comment removed",
    "task.attachment_added": "Attachment added",
    "task.attachment_removed": "Attachment removed",
    "task.unblocked": "Task unblocked",
    "dependency.added": "Dependency added",
    "dependency.removed": "Dependency removed",
  };
  return map[action] ?? action.replace(/_/g, " ");
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-faint">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
