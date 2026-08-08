"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Star, Users, UserPlus } from "lucide-react";

import { api } from "@/lib/api";
import {
  addFavorite,
  createEmployee,
  getOrganizationStructure,
  listEmployees,
  listSkills,
  removeFavorite,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import type { Department, EmployeeSummary, Location, OrganizationStructure, Skill, Team } from "@/types";
import { useAuth } from "@/hooks/useAuth";import { PageHeader, StatCard } from "@/components/ui/PageHeader";
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

const AVAILABILITY_OPTIONS = ["available", "busy", "meeting", "leave", "focus", "offline", "remote", "traveling"];
const PRESENCE_OPTIONS = ["online", "away", "busy", "offline"];
const STATUS_OPTIONS = ["active", "probation", "notice", "inactive"];
const SORT_OPTIONS = [
  { value: "name", label: "Name" },
  { value: "recent", label: "Recently joined" },
  { value: "expertise", label: "Expertise" },
  { value: "department", label: "Department" },
];

function presenceDot(status: string | null | undefined, online: boolean): { label: string; cls: string } {
  if (online || status === "online") return { label: "Online", cls: "bg-emerald-500" };
  if (status === "busy") return { label: "Busy", cls: "bg-amber-500" };
  if (status === "away") return { label: "Away", cls: "bg-amber-400" };
  return { label: "Offline", cls: "bg-gray-300" };
}

export default function PeoplePage() {
  return (
    <Suspense fallback={null}>
      <PeopleContent />
    </Suspense>
  );
}

function PeopleContent() {
  const router = useRouter();
  const { can } = useAuth();
  const canHire = can(PERMISSIONS.EMPLOYEES_HIRE);
  const canFavorite = can(PERMISSIONS.FAVORITES_MANAGE);

  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [structure, setStructure] = useState<OrganizationStructure | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);

  const [query, setQuery] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [skill, setSkill] = useState("");
  const [availability, setAvailability] = useState("");
  const [presence, setPresence] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("name");
  const [showFavorites, setShowFavorites] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEmployees({
        department_id: departmentId || undefined,
        team_id: teamId || undefined,
        location_id: locationId || undefined,
        skill: skill || undefined,
        availability: availability || undefined,
        presence: presence || undefined,
        status: status || undefined,
        sort,
        page_size: 200,
      });
      const filtered = query.trim()
        ? data.filter((e) =>
            `${e.full_name} ${e.email} ${e.designation ?? ""} ${e.employee_number}`
              .toLowerCase()
              .includes(query.trim().toLowerCase())
          )
        : data;
      setEmployees(showFavorites ? filtered.filter((e) => e.is_favorite) : filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load employees");
    } finally {
      setLoading(false);
    }
  }, [query, departmentId, teamId, locationId, skill, availability, presence, status, sort, showFavorites]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    getOrganizationStructure().then(setStructure).catch(() => undefined);
    listSkills().then(setSkills).catch(() => undefined);
  }, []);

  async function toggleFavorite(employee: EmployeeSummary) {
    try {
      if (employee.is_favorite) {
        await removeFavorite(employee.id);
      } else {
        await addFavorite(employee.id);
      }
      setEmployees((prev) =>
        prev.map((e) => (e.id === employee.id ? { ...e, is_favorite: !e.is_favorite } : e))
      );
    } catch (err) {
      toastError("Failed to update favorite", err instanceof Error ? err.message : undefined);
    }
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFormError(null);
    const payload: Record<string, unknown> = {
      first_name: String(form.get("first_name") ?? "").trim(),
      last_name: String(form.get("last_name") ?? "").trim() || undefined,
      email: String(form.get("email") ?? "").trim(),
      designation: String(form.get("designation") ?? "").trim() || undefined,
      employee_number: String(form.get("employee_number") ?? "").trim() || undefined,
      department_id: String(form.get("department_id") ?? "") || undefined,
      team_id: String(form.get("team_id") ?? "") || undefined,
      location_id: String(form.get("location_id") ?? "") || undefined,
      manager_id: String(form.get("manager_id") ?? "") || undefined,
      employment_type: String(form.get("employment_type") ?? "full_time"),
      joining_date: String(form.get("joining_date") ?? "") || undefined,
    };
    if (!payload.first_name || !payload.email) {
      setFormError("First name and email are required.");
      return;
    }
    setSaving(true);
    try {
      const created = await createEmployee(payload);
      toastSuccess("Employee created");
      setShowCreate(false);
      router.push(`/people/${created.id}`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create employee");
    } finally {
      setSaving(false);
    }
  }

  const departments = structure?.departments ?? [];
  const teams = useMemo(
    () => (structure?.teams ?? []).filter((t) => !departmentId || t.department_id === departmentId),
    [structure, departmentId]
  );
  const locations = structure?.locations ?? [];

  const managerOptions = useMemo(() => employees.filter((e) => e.status !== "inactive"), [employees]);
  const onlineCount = employees.filter((e) => e.is_online).length;
  const avgExpertise = employees.length
    ? Math.round(employees.reduce((sum, e) => sum + e.expertise_score, 0) / employees.length)
    : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="People"
        description="The living digital organization â€” everyone, everywhere, connected."
        actions={
          canHire ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <UserPlus className="h-4 w-4" /> Add employee
            </Button>
          ) : undefined
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total people" value={employees.length} icon={Users} hint="Active directory" />
        <StatCard label="Online now" value={onlineCount} icon={Star} hint="Live presence" />
        <StatCard label="Avg expertise" value={`${avgExpertise}/100`} icon={Star} hint="Across the org" />
      </div>

      <Card className="!p-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4">
          <div className="relative min-w-52 flex-1">
            <Input
              className="w-full"
              placeholder="Search by name, email, designation, or employee number..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SelectFilter value={departmentId} onChange={(v) => { setDepartmentId(v); setTeamId(""); }} label="Department" options={departments.map((d: Department) => ({ value: d.id, label: d.name }))} />
            <SelectFilter value={teamId} onChange={setTeamId} label="Team" options={teams.map((t: Team) => ({ value: t.id, label: t.name }))} />
            <SelectFilter value={locationId} onChange={setLocationId} label="Location" options={locations.map((l: Location) => ({ value: l.id, label: l.name }))} />
            <SelectFilter value={skill} onChange={setSkill} label="Skill" options={skills.map((s) => ({ value: s.name, label: s.name }))} />
            <SelectFilter value={availability} onChange={setAvailability} label="Availability" options={AVAILABILITY_OPTIONS.map((v) => ({ value: v, label: v }))} />
            <SelectFilter value={presence} onChange={setPresence} label="Presence" options={PRESENCE_OPTIONS.map((v) => ({ value: v, label: v }))} />
            <SelectFilter value={status} onChange={setStatus} label="Status" options={STATUS_OPTIONS.map((v) => ({ value: v, label: v }))} />
            <SelectFilter value={sort} onChange={setSort} label="Sort" options={SORT_OPTIONS} />
          </div>
        </div>

        {error ? (
          <ErrorState title="Could not load people" message={error} />
        ) : loading ? (
          <div className="flex justify-center py-24"><Spinner label="Loading people" /></div>
        ) : employees.length === 0 ? (
          <EmptyState
            icon={Users}
            title={showFavorites ? "No favorites yet" : "No people found"}
            description={
              showFavorites
                ? "Star someone in the directory to pin them here."
                : "Adjust your filters, or add the first employee to start building the org."
            }
            action={
              !showFavorites && canHire ? (
                <Button size="sm" onClick={() => setShowCreate(true)}>
                  <UserPlus className="h-4 w-4" /> Add employee
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">
            {employees.map((employee) => {
              const dot = presenceDot(employee.presence_status, employee.is_online);
              return (
                <div key={employee.id} className="card group relative p-4 transition-shadow hover:shadow-popover">
                  <div className="flex items-start gap-3">
                    <Link href={`/people/${employee.id}`}>
                      <Avatar name={employee.full_name} src={employee.avatar_url} size="md" />
                    </Link>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <Link href={`/people/${employee.id}`} className="truncate font-semibold text-ink hover:text-brand">
                          {employee.full_name}
                        </Link>
                        <span className={`h-2 w-2 shrink-0 rounded-full ${dot.cls}`} title={dot.label} />
                      </div>
                      <p className="truncate text-[13px] text-muted">{employee.designation || "No designation"}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {employee.department_name && <Badge tone="brand">{employee.department_name}</Badge>}
                        {employee.team_name && <Badge>{employee.team_name}</Badge>}
                        {employee.availability_status && employee.availability_status !== "available" && (
                          <Badge tone={employee.availability_status === "leave" ? "warning" : "neutral"}>
                            {employee.availability_status}
                          </Badge>
                        )}
                      </div>
                    </div>
                    {canFavorite && (
                      <button
                        className={`icon-btn ${employee.is_favorite ? "text-amber-500" : ""}`}
                        onClick={() => toggleFavorite(employee)}
                        aria-label={employee.is_favorite ? "Remove from favorites" : "Add to favorites"}
                      >
                        <Star className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-xs">
                    <span className="text-faint">Joined {formatDate(employee.joining_date)}</span>
                    {employee.expertise_score > 0 && (
                      <span className="font-semibold text-brand">Expertise {employee.expertise_score}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Add employee" description="Create a living profile â€” skills, relationships, and history follow.">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="First name" name="first_name" required placeholder="Ada" />
            <Input label="Last name" name="last_name" placeholder="Lovelace" />
          </div>
          <Input label="Work email" name="email" type="email" required placeholder="ada@company.com" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Designation" name="designation" placeholder="Senior Engineer" />
            <Input label="Employee number" name="employee_number" placeholder="VCOS-042" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Department" name="department_id" options={departments.map((d: Department) => ({ value: d.id, label: d.name }))} />
            <SelectField label="Team" name="team_id" options={teams.map((t: Team) => ({ value: t.id, label: t.name }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Location" name="location_id" options={locations.map((l: Location) => ({ value: l.id, label: l.name }))} />
            <SelectField
              label="Manager"
              name="manager_id"
              options={managerOptions.map((e) => ({ value: e.id, label: e.full_name }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField
              label="Employment type"
              name="employment_type"
              options={["full_time", "part_time", "contract", "intern", "freelance"].map((v) => ({ value: v, label: v }))}
            />
            <Input label="Joining date" name="joining_date" type="date" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create employee</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function SelectFilter({
  value,
  onChange,
  label,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-lg border border-line bg-elevated px-2.5 text-[13px] text-ink outline-none focus:border-brand"
      aria-label={label}
    >
      <option value="">{label}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}

function SelectField({ label, name, options }: { label: string; name: string; options: { value: string; label: string }[] }) {
  return (
    <label className="block text-[13px] font-medium text-muted">
      {label}
      <select
        name={name}
        className="mt-1.5 h-9 w-full rounded-lg border border-line bg-elevated px-2.5 text-[13px] text-ink outline-none focus:border-brand"
      >
        <option value="">None</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}
