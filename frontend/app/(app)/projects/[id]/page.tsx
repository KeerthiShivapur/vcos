"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  Flag,
  FolderKanban,
  Layers,
  ListChecks,
  Plus,
  Rocket,
  ShieldAlert,
  Trash2,
  Users,
} from "lucide-react";

import {
  addProjectMember,
  closeRisk,
  completeMilestone,
  completeSprint,
  createEpic,
  createMilestone,
  createRisk,
  createSprint,
  getProject,
  getProjectHealth,
  getProjectStats,
  getProjectTimeline,
  listEmployees,
  listEpics,
  listMeetings,
  listMilestones,
  listProjectMembers,
  listRisks,
  listSprints,
  listTasks,
  removeProjectMember,
  startSprint,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Epic, EmployeeSummary, Meeting, Milestone, Project, ProjectHealth, ProjectMember, ProjectStats, Risk, Sprint, Task, TimelineEntry } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate, formatDateTime, timeAgo, titleCase } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function ProjectDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailContent />
    </Suspense>
  );
}

function DetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.PROJECTS_MANAGE);

  const [project, setProject] = useState<Project | null>(null);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [health, setHealth] = useState<ProjectHealth | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [epics, setEpics] = useState<Epic[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("overview");

  const [showAddMember, setShowAddMember] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [showEpicModal, setShowEpicModal] = useState(false);
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [showSprintModal, setShowSprintModal] = useState(false);
  const [showRiskModal, setShowRiskModal] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [projectData, statsData, healthData, memberList, timelineList, epicList, milestoneList, sprintList, taskList, empList, meetingList, riskList] =
        await Promise.all([
          getProject(id),
          getProjectStats(id).catch(() => null),
          getProjectHealth(id).catch(() => null),
          listProjectMembers(id),
          getProjectTimeline(id).catch(() => [] as TimelineEntry[]),
          listEpics(id),
          listMilestones(id),
          listSprints(id),
          listTasks({ project_id: id }),
          listEmployees({ page_size: 200 }),
          listMeetings({ project_id: id }),
          listRisks({ project_id: id }),
        ]);
      setProject(projectData);
      setStats(statsData);
      setHealth(healthData);
      setMembers(memberList);
      setTimeline(timelineList);
      setEpics(epicList);
      setMilestones(milestoneList);
      setSprints(sprintList);
      setTasks(taskList);
      setEmployees(empList);
      setMeetings(meetingList);
      setRisks(riskList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load project");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleAddMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const employeeId = String(form.get("employee_id") ?? "");
    if (!employeeId) return;
    setSaving(true);
    setFormError(null);
    try {
      await addProjectMember(id, employeeId, String(form.get("role") ?? "") || undefined);
      toastSuccess("Member added");
      setShowAddMember(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to add member");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveMember(employeeId: string) {
    try {
      await removeProjectMember(id, employeeId);
      toastSuccess("Member removed");
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to remove member");
    }
  }

  async function handleCreateEpic(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setFormError(null);
    try {
      await createEpic({
        project_id: id,
        name: String(form.get("name") ?? ""),
        description: String(form.get("description") ?? "").trim() || undefined,
        priority: String(form.get("priority") ?? "medium"),
      });
      toastSuccess("Epic created");
      setShowEpicModal(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create epic");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateMilestone(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setFormError(null);
    try {
      await createMilestone({
        project_id: id,
        name: String(form.get("name") ?? ""),
        description: String(form.get("description") ?? "").trim() || undefined,
        due_date: String(form.get("due_date") ?? "") || undefined,
      });
      toastSuccess("Milestone created");
      setShowMilestoneModal(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create milestone");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateSprint(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setFormError(null);
    try {
      await createSprint({
        project_id: id,
        name: String(form.get("name") ?? ""),
        goal: String(form.get("goal") ?? "").trim() || undefined,
        start_date: String(form.get("start_date") ?? "") || undefined,
        end_date: String(form.get("end_date") ?? "") || undefined,
      });
      toastSuccess("Sprint created");
      setShowSprintModal(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create sprint");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateRisk(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setFormError(null);
    try {
      await createRisk({
        project_id: id,
        title: String(form.get("title") ?? ""),
        description: String(form.get("description") ?? "").trim() || undefined,
        probability: Number(form.get("probability") ?? 2),
        impact: Number(form.get("impact") ?? 2),
        owner_id: String(form.get("owner_id") ?? "") || undefined,
        mitigation: String(form.get("mitigation") ?? "").trim() || undefined,
      });
      toastSuccess("Risk logged");
      setShowRiskModal(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create risk");
    } finally {
      setSaving(false);
    }
  }

  async function handleCloseRisk(riskId: string) {
    try {
      await closeRisk(riskId);
      toastSuccess("Risk closed");
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to close risk");
    }
  }

  if (error) return <ErrorState title="Could not load project" message={error} />;
  if (loading || !project) return <div className="flex justify-center py-24"><Spinner label="Loading project" /></div>;

  const healthTone = health?.status === "good" ? "success" : health?.status === "watch" ? "warning" : "danger";

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Projects"
        title={project.name}
        description={project.description ?? `${project.code} — owned by ${project.owner_name ?? "no owner"}`}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={statusTone(project.status)}>{project.status}</Badge>
            <Badge tone={project.priority === "critical" ? "danger" : project.priority === "high" ? "warning" : "neutral"}>
              {project.priority}
            </Badge>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Progress" value={`${project.progress}%`} hint={`${project.completed_count} of ${project.tasks_count} tasks done`} icon={CheckCircle2} />
        <StatCard label="Health" value={health ? `${health.health}/100` : project.health} hint={health?.signals.length ? health.signals[0] : "No active signals"} icon={AlertTriangle} />
        <StatCard label="Members" value={project.members_count} hint={project.team_name ?? "Team not set"} icon={Users} />
        <StatCard label="Timeline" value={`${formatDate(project.start_date)} → ${formatDate(project.end_date)}`} hint={project.budget ? `Budget ${project.budget}` : "No budget"} icon={CalendarClock} />
      </div>

      {health && health.signals.length > 0 && (
        <div className={`rounded-xl border px-4 py-3 text-[13px] ${healthTone === "danger" ? "border-danger/30 bg-danger/10 text-danger" : healthTone === "warning" ? "border-warning/30 bg-warning/10 text-warning" : "border-success/30 bg-success/10 text-success"}`}>
          <span className="font-semibold">Health signals:</span> {health.signals.join(" · ")}
        </div>
      )}

      <Tabs
        tabs={[
          { id: "overview", label: "Overview", icon: FolderKanban },
          { id: "structure", label: "Structure", icon: Layers, count: epics.length + milestones.length + sprints.length },
          { id: "tasks", label: "Tasks", icon: ListChecks, count: tasks.length },
          { id: "meetings", label: "Meetings", icon: CalendarDays, count: meetings.length },
          { id: "risks", label: "Risks", icon: ShieldAlert, count: risks.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "overview" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card title="Stats" subtitle="Task flow and milestones at a glance">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                {[
                  ["Total tasks", stats?.total_tasks ?? project.tasks_count],
                  ["Completed", stats?.completed_tasks ?? project.completed_count],
                  ["In progress", stats?.in_progress_tasks ?? 0],
                  ["Blocked", stats?.blocked_tasks ?? 0],
                  ["Milestones", `${stats?.milestones_completed ?? 0}/${stats?.milestones_total ?? 0}`],
                  ["Overdue tasks", health?.overdue_tasks ?? 0],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-lg bg-canvas p-3">
                    <p className="text-xs text-faint">{label}</p>
                    <p className="mt-0.5 text-lg font-semibold text-ink">{value}</p>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Timeline" subtitle="Recent activity on this project">
              {timeline.length === 0 ? (
                <EmptyState icon={ListChecks} title="No activity yet" description="Project events will show up here." />
              ) : (
                <ul className="space-y-0">
                  {timeline.slice(0, 12).map((entry) => (
                    <li key={entry.id} className="flex items-start gap-3 border-b border-line py-2.5 last:border-0">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-medium text-ink">{entry.title}</p>
                        {entry.description && <p className="text-[12px] text-muted">{entry.description}</p>}
                      </div>
                      <span className="shrink-0 text-[11px] text-faint">{timeAgo(entry.occurred_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
          <div className="space-y-6">
            <Card title="Members" actions={canManage ? <Button size="sm" onClick={() => setShowAddMember(true)}><Plus className="h-3.5 w-3.5" /> Add</Button> : undefined}>
              {members.length === 0 ? (
                <EmptyState icon={Users} title="No members" description="Add people to collaborate." />
              ) : (
                <ul className="space-y-3">
                  {members.map((member) => (
                    <li key={member.id} className="flex items-center gap-2.5">
                      <Avatar name={member.name} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-ink">{member.name}</p>
                        <p className="truncate text-[11px] text-faint">{member.designation ?? member.role ?? "Member"}</p>
                      </div>
                      {canManage && (
                        <button onClick={() => handleRemoveMember(member.employee_id)} className="rounded-lg p-1 text-faint hover:bg-danger/10 hover:text-danger" title="Remove member">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {health && (
              <Card title="Risks" subtitle="Top open risks by score">
                {health.risks.length === 0 ? (
                  <p className="py-6 text-center text-[13px] text-faint">No open risks.</p>
                ) : (
                  <ul className="space-y-2.5">
                    {health.risks.map((risk) => (
                      <li key={risk.id} className="flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate text-[13px] text-ink">{risk.title}</span>
                        <Badge tone={risk.severity === "critical" || risk.severity === "high" ? "danger" : risk.severity === "medium" ? "warning" : "neutral"}>
                          {risk.risk_score} · {risk.severity}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === "structure" && (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2">
            {canManage && (
              <>
                <Button size="sm" variant="secondary" onClick={() => setShowEpicModal(true)}><Plus className="h-4 w-4" /> Epic</Button>
                <Button size="sm" variant="secondary" onClick={() => setShowMilestoneModal(true)}><Plus className="h-4 w-4" /> Milestone</Button>
                <Button size="sm" variant="secondary" onClick={() => setShowSprintModal(true)}><Plus className="h-4 w-4" /> Sprint</Button>
              </>
            )}
          </div>

          <Card title="Epics" subtitle={`${epics.length} epics`}>
            {epics.length === 0 ? (
              <EmptyState icon={Layers} title="No epics" description="Epics group related work streams." />
            ) : (
              <ul className="divide-y divide-line">
                {epics.map((epic) => (
                  <li key={epic.id} className="flex items-center gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">{epic.name}</p>
                      {epic.description && <p className="truncate text-[12px] text-muted">{epic.description}</p>}
                    </div>
                    <span className="text-[12px] text-faint">{epic.tasks_count} tasks</span>
                    <Badge tone={statusTone(epic.status)}>{epic.status}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Milestones" subtitle="Key checkpoints">
              {milestones.length === 0 ? (
                <EmptyState icon={Flag} title="No milestones" />
              ) : (
                <ul className="divide-y divide-line">
                  {milestones.map((milestone) => (
                    <li key={milestone.id} className="flex items-center gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-ink">{milestone.name}</p>
                        <p className="text-[12px] text-faint">Due {formatDate(milestone.due_date)}</p>
                      </div>
                      <Badge tone={statusTone(milestone.status)}>{milestone.status}</Badge>
                      {canManage && milestone.status !== "completed" && (
                        <Button size="sm" variant="ghost" onClick={async () => { await completeMilestone(milestone.id); toastSuccess("Milestone completed"); await load(); }}>
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Sprints" subtitle="Time-boxed delivery cycles">
              {sprints.length === 0 ? (
                <EmptyState icon={Rocket} title="No sprints" />
              ) : (
                <ul className="divide-y divide-line">
                  {sprints.map((sprint) => (
                    <li key={sprint.id} className="flex items-center gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-ink">{sprint.name}</p>
                        <p className="text-[12px] text-faint">
                          {formatDate(sprint.start_date)} → {formatDate(sprint.end_date)}
                        </p>
                      </div>
                      <Badge tone={statusTone(sprint.status)}>{sprint.status}</Badge>
                      {canManage && sprint.status === "planned" && (
                        <Button size="sm" variant="ghost" onClick={async () => { await startSprint(sprint.id); toastSuccess("Sprint started"); await load(); }}>Start</Button>
                      )}
                      {canManage && sprint.status === "active" && (
                        <Button size="sm" variant="ghost" onClick={async () => { await completeSprint(sprint.id); toastSuccess("Sprint completed"); await load(); }}>Complete</Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}

      {tab === "tasks" && (
        <Card title="Tasks" subtitle="All tasks in this project" bodyClassName="p-0"
          actions={<Button size="sm" variant="secondary" onClick={() => window.location.assign(`/tasks?project_id=${id}`)}>Open task board</Button>}>
          {tasks.length === 0 ? (
            <div className="p-5"><EmptyState icon={ListChecks} title="No tasks" description="Create tasks to start executing." /></div>
          ) : (
            <ul className="divide-y divide-line">
              {tasks.map((task) => (
                <li key={task.id}>
                  <Link href={`/tasks/${task.id}`} className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-canvas/60">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">{task.title}</p>
                      <p className="text-[12px] text-faint">{task.project_name ?? titleCase(task.status)} · {task.assignee_name ?? "Unassigned"}</p>
                    </div>
                    <Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : "neutral"}>{task.priority}</Badge>
                    <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === "meetings" && (
        <Card title="Meetings" subtitle={`${meetings.length} meetings linked to this project`} bodyClassName="p-0">
          {meetings.length === 0 ? (
            <div className="p-5">
              <EmptyState icon={CalendarDays} title="No meetings yet" description="Schedule a meeting and link it to this project." action={
                <Button size="sm" variant="secondary" onClick={() => window.location.assign("/meetings")}>Open meetings</Button>
              } />
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {meetings.map((meeting) => (
                <li key={meeting.id}>
                  <Link href={`/meetings/${meeting.id}`} className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-canvas/60">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">{meeting.title}</p>
                      <p className="text-[12px] text-faint">
                        {titleCase(meeting.meeting_type)} · {formatDateTime(meeting.start_at)}
                      </p>
                    </div>
                    <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === "risks" && (
        <Card title="Risks" subtitle="Probability × impact scoring with mitigation"
          actions={canManage ? <Button size="sm" onClick={() => setShowRiskModal(true)}><Plus className="h-4 w-4" /> Log risk</Button> : undefined}>
          {risks.length === 0 ? (
            <EmptyState icon={ShieldAlert} title="No risks logged" description="Log risks so the health signal stays honest." />
          ) : (
            <ul className="space-y-3">
              {risks.map((risk) => (
                <li key={risk.id} className="flex items-start gap-3 rounded-lg border border-line p-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-semibold text-ink">{risk.title}</p>
                    {risk.description && <p className="mt-0.5 text-[12px] text-muted">{risk.description}</p>}
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-faint">
                      <span>P{risk.probability} × I{risk.impact} = {risk.risk_score}</span>
                      <span>· {risk.owner_name ?? "Unassigned"}</span>
                      {risk.mitigation && <span>· Mitigation: {risk.mitigation}</span>}
                      {risk.due_at && <span>· Due {formatDate(risk.due_at)}</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge tone={risk.severity === "critical" || risk.severity === "high" ? "danger" : risk.severity === "medium" ? "warning" : "neutral"}>
                      {risk.severity}
                    </Badge>
                    <Badge tone={statusTone(risk.status)}>{risk.status}</Badge>
                    {canManage && risk.status !== "closed" && (
                      <Button size="sm" variant="ghost" onClick={() => handleCloseRisk(risk.id)}>
                        <CheckCircle2 className="h-3.5 w-3.5" /> Close
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Modal open={showAddMember} onClose={() => setShowAddMember(false)} title="Add member" description="Add someone to this project.">
        <form onSubmit={handleAddMember} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Select label="Employee" name="employee_id" required options={employees
            .filter((e) => !members.some((m) => m.employee_id === e.id))
            .map((e) => ({ value: e.id, label: `${e.full_name} — ${e.designation ?? e.department_name ?? ""}` }))} />
          <Select label="Role" name="role" options={["owner", "lead", "member", "reviewer"].map((r) => ({ value: r, label: r }))} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowAddMember(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Add member</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showEpicModal} onClose={() => setShowEpicModal(false)} title="New epic" description="Group related work streams.">
        <form onSubmit={handleCreateEpic} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Name" name="name" required placeholder="Mobile app" />
          <TextareaField label="Description" name="description" rows={3} />
          <Select label="Priority" name="priority" defaultValue="medium" options={["low", "medium", "high", "critical"].map((s) => ({ value: s, label: s }))} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowEpicModal(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create epic</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showMilestoneModal} onClose={() => setShowMilestoneModal(false)} title="New milestone" description="Set a key checkpoint.">
        <form onSubmit={handleCreateMilestone} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Name" name="name" required placeholder="Beta cutoff" />
          <TextareaField label="Description" name="description" rows={3} />
          <Input label="Due date" name="due_date" type="date" />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowMilestoneModal(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create milestone</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showSprintModal} onClose={() => setShowSprintModal(false)} title="New sprint" description="Time-boxed delivery cycle.">
        <form onSubmit={handleCreateSprint} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Name" name="name" required placeholder="Sprint 12" />
          <Input label="Goal" name="goal" placeholder="Ship checkout v2" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Start date" name="start_date" type="date" />
            <Input label="End date" name="end_date" type="date" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowSprintModal(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create sprint</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showRiskModal} onClose={() => setShowRiskModal(false)} title="Log risk" description="Probability × impact drives the health signal.">
        <form onSubmit={handleCreateRisk} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Title" name="title" required placeholder="Vendor delivery delay" />
          <TextareaField label="Description" name="description" rows={2} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Probability (1-5)" name="probability" type="number" min={1} max={5} defaultValue={2} />
            <Input label="Impact (1-5)" name="impact" type="number" min={1} max={5} defaultValue={2} />
          </div>
          <Select label="Owner" name="owner_id" options={employees.map((e) => ({ value: e.id, label: e.full_name }))} />
          <TextareaField label="Mitigation" name="mitigation" rows={2} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowRiskModal(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Log risk</Button>
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
