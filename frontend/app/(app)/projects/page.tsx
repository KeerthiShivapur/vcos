"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { FolderKanban, Plus } from "lucide-react";

import { createProject, listDepartments, listEmployees, listProjects, listRoadmaps, listTeams } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Department, EmployeeSummary, Project, Roadmap, Team } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
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
import { toastSuccess } from "@/components/ui/Toaster";

export default function ProjectsPage() {
  return (
    <Suspense fallback={null}>
      <ProjectsContent />
    </Suspense>
  );
}

function ProjectsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.PROJECTS_MANAGE);

  const [projects, setProjects] = useState<Project[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [roadmaps, setRoadmaps] = useState<Roadmap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [projectList, empList, deptList, teamList, roadmapList] = await Promise.all([
        listProjects(),
        listEmployees({ page_size: 200 }),
        listDepartments().catch(() => [] as Department[]),
        listTeams().catch(() => [] as Team[]),
        listRoadmaps().catch(() => [] as Roadmap[]),
      ]);
      setProjects(projectList);
      setEmployees(empList);
      setDepartments(deptList);
      setTeams(teamList);
      setRoadmaps(roadmapList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFormError(null);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      setFormError("Project name is required.");
      return;
    }
    setSaving(true);
    try {
      await createProject({
        name,
        code: String(form.get("code") ?? "").trim() || undefined,
        description: String(form.get("description") ?? "").trim() || undefined,
        status: String(form.get("status") ?? "draft") || "draft",
        priority: String(form.get("priority") ?? "medium") || "medium",
        owner_id: String(form.get("owner_id") ?? "") || undefined,
        department_id: String(form.get("department_id") ?? "") || undefined,
        team_id: String(form.get("team_id") ?? "") || undefined,
        roadmap_id: String(form.get("roadmap_id") ?? "") || undefined,
        start_date: String(form.get("start_date") ?? "") || undefined,
        end_date: String(form.get("end_date") ?? "") || undefined,
        budget: form.get("budget") ? Number(form.get("budget")) : undefined,
      });
      toastSuccess("Project created");
      setShowCreate(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create project");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Projects"
        description="Roadmaps, epics, milestones and sprints — the work engine."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> New project
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState title="Could not load projects" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading projects" /></div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="No projects yet"
          description="Create your first project to start tracking work."
          action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> New project</Button> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <Link key={project.id} href={`/projects/${project.id}`} className="card group flex flex-col p-5 transition-shadow hover:shadow-popover">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
                    <FolderKanban className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold text-ink group-hover:text-brand">{project.name}</h3>
                    <p className="text-[12px] text-faint">{project.code || project.priority}</p>
                  </div>
                </div>
                <Badge tone={statusTone(project.status)}>{project.status}</Badge>
              </div>
              {project.description && (
                <p className="mt-3 line-clamp-2 text-[13px] leading-relaxed text-muted">{project.description}</p>
              )}
              <div className="mt-4">
                <div className="flex items-center justify-between text-[12px] text-faint">
                  <span>{project.completed_count} / {project.tasks_count} tasks</span>
                  <span className={project.health === "good" ? "text-success" : project.health === "watch" ? "text-warning" : "text-danger"}>
                    {project.health}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-canvas">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${project.progress}%` }} />
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
                <span className="text-[12px] text-faint">{project.members_count} member{project.members_count === 1 ? "" : "s"}</span>
                {project.owner_name ? (
                  <span className="flex items-center gap-1.5 text-[12px] font-medium text-muted">
                    <Avatar name={project.owner_name} size="sm" /> {project.owner_name}
                  </span>
                ) : <span className="text-[12px] text-faint">No owner</span>}
              </div>
            </Link>
          ))}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New project" description="Start with the basics — structure comes next." size="lg">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Name" name="name" required placeholder="Atlas launch" />
            <Input label="Code" name="code" placeholder="ATLAS" />
          </div>
          <Textarea label="Description" name="description" rows={3} placeholder="What is this project about?" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Status" name="status" defaultValue="draft"
              options={["draft", "active", "paused", "completed", "archived"].map((s) => ({ value: s, label: s }))} />
            <Select label="Priority" name="priority" defaultValue="medium"
              options={["low", "medium", "high", "critical"].map((s) => ({ value: s, label: s }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Owner" name="owner_id" options={employees.map((e) => ({ value: e.id, label: e.full_name }))} />
            <Select label="Roadmap" name="roadmap_id" options={roadmaps.map((r) => ({ value: r.id, label: r.name }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Department" name="department_id" options={departments.map((d) => ({ value: d.id, label: d.name }))} />
            <Select label="Team" name="team_id" options={teams.map((t) => ({ value: t.id, label: t.name }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Input label="Start date" name="start_date" type="date" />
            <Input label="End date" name="end_date" type="date" />
            <Input label="Budget" name="budget" type="number" min={0} step="0.01" placeholder="0.00" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create project</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
