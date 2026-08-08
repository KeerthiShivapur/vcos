"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Plus, Trash2, UserSquare2, Users } from "lucide-react";

import {
  addTeamGoal,
  addTeamMember,
  getTeam,
  listEmployees,
  listTeamGoals,
  removeTeamMember,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { EmployeeSummary, Team, TeamMember } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

interface TeamGoal {
  id: string;
  team_id: string;
  title: string;
  status: string;
  created_at: string;
}

export default function TeamDetailPage() {
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
  const canManage = roleCan(user?.role, PERMISSIONS.TEAM_MANAGE);

  const [team, setTeam] = useState<Team | null>(null);
  const [goals, setGoals] = useState<TeamGoal[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showAddMember, setShowAddMember] = useState(false);
  const [selectedMember, setSelectedMember] = useState("");
  const [saving, setSaving] = useState(false);
  const [showGoalModal, setShowGoalModal] = useState(false);
  const [goalTitle, setGoalTitle] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [teamData, goalList, empList] = await Promise.all([
        getTeam(id),
        listTeamGoals(id).catch(() => [] as TeamGoal[]),
        listEmployees({ page_size: 200 }),
      ]);
      setTeam(teamData);
      setGoals(goalList);
      setEmployees(empList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load team");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleAddMember() {
    if (!selectedMember) return;
    setSaving(true);
    try {
      await addTeamMember(id, selectedMember);
      toastSuccess("Member added");
      setShowAddMember(false);
      setSelectedMember("");
      await load();
    } catch (err) {
      toastError("Failed to add member", err instanceof Error ? err.message : undefined);
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveMember(member: TeamMember) {
    if (!confirm(`Remove ${member.employee_name} from this team?`)) return;
    try {
      await removeTeamMember(id, member.employee_id);
      toastSuccess("Member removed");
      await load();
    } catch (err) {
      toastError("Failed to remove member", err instanceof Error ? err.message : undefined);
    }
  }

  async function handleAddGoal(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goalTitle.trim()) return;
    setSaving(true);
    try {
      await addTeamGoal(id, goalTitle.trim());
      toastSuccess("Goal added");
      setShowGoalModal(false);
      setGoalTitle("");
      const goalList = await listTeamGoals(id);
      setGoals(goalList);
    } catch (err) {
      toastError("Failed to add goal", err instanceof Error ? err.message : undefined);
    } finally {
      setSaving(false);
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader title="Team" breadcrumb="Teams" />
        <ErrorState title="Could not load team" message={error} />
      </div>
    );
  }

  if (loading || !team) {
    return (
      <div className="space-y-6">
        <PageHeader title="Team" breadcrumb="Teams" />
        <div className="flex justify-center py-24"><Spinner label="Loading team" /></div>
      </div>
    );
  }

  const memberIds = new Set(team.members.map((m) => m.employee_id));
  const available = employees.filter((e) => !memberIds.has(e.id) && e.status !== "inactive");

  return (
    <div className="space-y-6">
      <PageHeader
        title={team.name}
        breadcrumb="Teams"
        description={team.description ?? "No description provided."}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Members" value={team.members_count} icon={Users} />
        <StatCard label="Department" value={team.department_name ?? "—"} icon={UserSquare2} />
        <StatCard label="Goals" value={goals.length} icon={UserSquare2} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Members"
          subtitle={`${team.members.length} people`}
          actions={
            canManage ? (
              <Button size="sm" variant="secondary" onClick={() => { setShowAddMember(true); setSelectedMember(""); }}>
                <Plus className="h-4 w-4" /> Add member
              </Button>
            ) : undefined
          }
        >
          {team.members.length === 0 ? (
            <EmptyState icon={Users} title="No members yet" description="Add people to bring the team to life." />
          ) : (
            <ul className="space-y-2">
              {team.members.map((member) => (
                <li key={member.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2.5">
                  <Avatar name={member.employee_name} src={member.avatar_url} size="sm" />
                  <div className="min-w-0 flex-1">
                    <Link href={`/people/${member.employee_id}`} className="truncate text-[13px] font-medium text-ink hover:text-brand">
                      {member.employee_name}
                    </Link>
                    <p className="truncate text-[11px] text-faint">
                      {member.designation || "Employee"}
                      {member.role ? ` · ${member.role}` : ""}
                      {member.joined_at ? ` · joined ${formatDate(member.joined_at)}` : ""}
                    </p>
                  </div>
                  {member.employee_id === team.lead_id && <Badge tone="brand">Lead</Badge>}
                  {canManage && member.employee_id !== team.lead_id && (
                    <button className="icon-btn hover:!text-danger" onClick={() => handleRemoveMember(member)} aria-label="Remove member">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Goals"
          subtitle="Team objectives"
          actions={
            canManage ? (
              <Button size="sm" variant="secondary" onClick={() => setShowGoalModal(true)}>
                <Plus className="h-4 w-4" /> Add goal
              </Button>
            ) : undefined
          }
        >
          {goals.length === 0 ? (
            <EmptyState icon={UserSquare2} title="No goals yet" description="Track what this team is working toward." />
          ) : (
            <ul className="space-y-2">
              {goals.map((goal) => (
                <li key={goal.id} className="flex items-center justify-between gap-3 rounded-xl border border-line px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">{goal.title}</p>
                    <p className="text-[11px] text-faint">{formatDate(goal.created_at)}</p>
                  </div>
                  <Badge tone={goal.status === "completed" ? "success" : goal.status === "in_progress" ? "brand" : "neutral"}>
                    {goal.status}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Modal open={showAddMember} onClose={() => setShowAddMember(false)} title="Add team member">
        <div className="space-y-4">
          <label className="block text-[13px] font-medium text-muted">
            Employee
            <select
              value={selectedMember}
              onChange={(e) => setSelectedMember(e.target.value)}
              className="mt-1.5 h-9 w-full rounded-lg border border-line bg-elevated px-2.5 text-[13px] text-ink outline-none focus:border-brand"
            >
              <option value="">Select an employee</option>
              {available.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.full_name} — {employee.designation || "Employee"}
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setShowAddMember(false)}>Cancel</Button>
            <Button loading={saving} onClick={handleAddMember} disabled={!selectedMember}>Add member</Button>
          </div>
        </div>
      </Modal>

      <Modal open={showGoalModal} onClose={() => setShowGoalModal(false)} title="Add team goal">
        <form onSubmit={handleAddGoal} className="space-y-4">
          <Input label="Goal" required placeholder="Ship the Q3 platform release" value={goalTitle} onChange={(e) => setGoalTitle(e.target.value)} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowGoalModal(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Add goal</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
