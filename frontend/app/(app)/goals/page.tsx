"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Target } from "lucide-react";

import { createGoal, listDepartments, listEmployees, listGoals, listProjects, listTeams } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Department, EmployeeSummary, Goal, Project, Team } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export default function GoalsPage() {
  return (
    <Suspense fallback={null}>
      <GoalsContent />
    </Suspense>
  );
}

function GoalsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.GOALS_MANAGE);

  const [goals, setGoals] = useState<Goal[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [scope, setScope] = useState("");
  const [status, setStatus] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [krCount, setKrCount] = useState(2);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [goalList, empList, deptList, teamList, projectList] = await Promise.all([
        listGoals({ scope: scope || undefined, status: status || undefined }),
        listEmployees({ page_size: 200 }),
        listDepartments().catch(() => [] as Department[]),
        listTeams().catch(() => [] as Team[]),
        listProjects().catch(() => [] as Project[]),
      ]);
      setGoals(goalList);
      setEmployees(empList);
      setDepartments(deptList);
      setTeams(teamList);
      setProjects(projectList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load goals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, status]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFormError(null);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      setFormError("Goal name is required.");
      return;
    }
    setSaving(true);
    try {
      const keyResults = [];
      for (let i = 1; i <= krCount; i++) {
        const title = String(form.get(`kr_${i}`) ?? "").trim();
        if (!title) continue;
        const target = form.get(`target_${i}`) ? Number(form.get(`target_${i}`)) : undefined;
        keyResults.push({
          title,
          target: target ?? undefined,
          unit: String(form.get(`unit_${i}`) ?? "").trim() || undefined,
          current: 0,
        });
      }
      await createGoal({
        name,
        description: String(form.get("description") ?? "").trim() || undefined,
        scope: String(form.get("scope") ?? "team"),
        status: String(form.get("status") ?? "planned"),
        priority: String(form.get("priority") ?? "medium"),
        owner_id: String(form.get("owner_id") ?? "") || undefined,
        department_id: String(form.get("department_id") ?? "") || undefined,
        team_id: String(form.get("team_id") ?? "") || undefined,
        project_id: String(form.get("project_id") ?? "") || undefined,
        start_date: String(form.get("start_date") ?? "") || undefined,
        end_date: String(form.get("end_date") ?? "") || undefined,
        key_results: keyResults.length ? keyResults : undefined,
      });
      toastSuccess("Goal created");
      setShowCreate(false);
      setKrCount(2);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create goal");
    } finally {
      setSaving(false);
    }
  }

  const scoped = scope === "company" || scope === "department" || scope === "team" || scope === "project";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Goals"
        description="Objectives and key results across the company."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> New goal
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Select className="h-9 w-40" aria-label="Scope" options={["company", "department", "team", "project", "personal"].map((s) => ({ value: s, label: s }))}
          value={scope} onChange={(e) => setScope(e.target.value)} placeholder="All scopes" />
        <Select className="h-9 w-36" aria-label="Status" options={["planned", "in_progress", "completed", "at_risk"].map((s) => ({ value: s, label: s }))}
          value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses" />
      </div>

      {error ? (
        <ErrorState title="Could not load goals" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading goals" /></div>
      ) : goals.length === 0 ? (
        <EmptyState
          icon={Target}
          title="No goals yet"
          description="Set an objective and key results to track outcomes."
          action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> New goal</Button> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {goals.map((goal) => (
            <Link key={goal.id} href={`/goals/${goal.id}`} className="card group flex flex-col p-5 transition-shadow hover:shadow-popover">
              <div className="flex items-start justify-between gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand">
                  <Target className="h-4.5 w-4.5" />
                </div>
                <Badge tone={statusTone(goal.status)}>{goal.status}</Badge>
              </div>
              <h3 className="mt-3 truncate font-semibold text-ink group-hover:text-brand">{goal.name}</h3>
              <p className="mt-0.5 text-[12px] text-faint">
                {goal.scope} · {goal.owner_name ?? "No owner"}
              </p>
              {goal.description && <p className="mt-2 line-clamp-2 text-[13px] leading-relaxed text-muted">{goal.description}</p>}
              <div className="mt-4 flex items-center justify-between text-[12px] text-faint">
                <span>{goal.key_results_count} key result{goal.key_results_count === 1 ? "" : "s"}</span>
                <span>{formatDate(goal.end_date)}</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-canvas">
                <div className="h-full rounded-full bg-brand" style={{ width: `${Math.round(goal.progress)}%` }} />
              </div>
            </Link>
          ))}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New goal" description="Objectives with measurable key results." size="lg">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Name" name="name" required placeholder="Grow to 10k customers" />
          <Textarea label="Description" name="description" rows={2} />
          <div className="grid gap-4 sm:grid-cols-3">
            <Select label="Scope" name="scope" defaultValue="team" options={["company", "department", "team", "project", "personal"].map((s) => ({ value: s, label: s }))} />
            <Select label="Status" name="status" defaultValue="planned" options={["planned", "in_progress", "completed", "at_risk"].map((s) => ({ value: s, label: s }))} />
            <Select label="Priority" name="priority" defaultValue="medium" options={["low", "medium", "high", "critical"].map((s) => ({ value: s, label: s }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Owner" name="owner_id" options={employees.map((e) => ({ value: e.id, label: e.full_name }))} />
            {scoped && scope === "department" && <Select label="Department" name="department_id" options={departments.map((d) => ({ value: d.id, label: d.name }))} />}
            {scoped && scope === "team" && <Select label="Team" name="team_id" options={teams.map((t) => ({ value: t.id, label: t.name }))} />}
            {scoped && scope === "project" && <Select label="Project" name="project_id" options={projects.map((p) => ({ value: p.id, label: p.name }))} />}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Start date" name="start_date" type="date" />
            <Input label="End date" name="end_date" type="date" />
          </div>
          <div className="rounded-lg border border-line p-4">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold text-ink">Key results</p>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" type="button" onClick={() => setKrCount((c) => c + 1)}>+ Add</Button>
                {krCount > 0 && <Button size="sm" variant="ghost" type="button" onClick={() => setKrCount((c) => Math.max(0, c - 1))}>− Remove</Button>}
              </div>
            </div>
            <div className="mt-3 space-y-3">
              {Array.from({ length: krCount }).map((_, index) => (
                <div key={index} className="grid gap-2 sm:grid-cols-[1fr_100px_80px]">
                  <Input name={`kr_${index + 1}`} placeholder="Key result title" />
                  <Input name={`target_${index + 1}`} type="number" min={0} placeholder="Target" />
                  <Input name={`unit_${index + 1}`} placeholder="Unit" />
                </div>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create goal</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
