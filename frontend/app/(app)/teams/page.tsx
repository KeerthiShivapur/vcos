"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, UserSquare2 } from "lucide-react";

import { createTeam, getOrganizationStructure, listTeams } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import type { OrganizationStructure, Team } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { toastSuccess } from "@/components/ui/Toaster";
import { EntitlementGate } from "@/hooks/useEntitlements";

export default function TeamsPage() {
  return (
    <Suspense fallback={null}>
      <TeamsContent />
    </Suspense>
  );
}

function TeamsContent() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.TEAM_MANAGE);

  const [teams, setTeams] = useState<Team[]>([]);
  const [structure, setStructure] = useState<OrganizationStructure | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [teamList, org] = await Promise.all([
        listTeams(),
        getOrganizationStructure(),
      ]);
      setTeams(teamList);
      setStructure(org);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load teams");
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
      setFormError("Team name is required.");
      return;
    }
    setSaving(true);
    try {
      await createTeam({
        name,
        code: String(form.get("code") ?? "").trim() || undefined,
        description: String(form.get("description") ?? "").trim() || undefined,
        department_id: String(form.get("department_id") ?? "") || undefined,
        lead_id: String(form.get("lead_id") ?? "") || undefined,
      });
      toastSuccess("Team created");
      setShowCreate(false);
      await load();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Unable to create team",
      );
    } finally {
      setSaving(false);
    }
  }

  const departments = structure?.departments ?? [];
  const leads = teams.flatMap((t) =>
    t.lead_id ? [{ value: t.lead_id, label: t.lead_name ?? t.lead_id }] : [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Teams"
        description="Cross-functional teams that ship the work."
        actions={
          canManage ? (
            <EntitlementGate
              entitlementKey="teams.max"
              required={1}
              fallback={
                <Button size="sm" variant="secondary" disabled>
                  Upgrade to create teams
                </Button>
              }
            >
              <Button size="sm" onClick={() => setShowCreate(true)}>
                <Plus className="h-4 w-4" /> Create team
              </Button>
            </EntitlementGate>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState title="Could not load teams" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading teams" />
        </div>
      ) : teams.length === 0 ? (
        <EmptyState
          icon={UserSquare2}
          title="No teams yet"
          description="Create your first team to organize work around people."
          action={
            canManage ? (
              <EntitlementGate
                entitlementKey="teams.max"
                required={1}
                fallback={
                  <Button size="sm" variant="secondary" disabled>
                    Upgrade to create teams
                  </Button>
                }
              >
                <Button size="sm" onClick={() => setShowCreate(true)}>
                  <Plus className="h-4 w-4" /> Create team
                </Button>
              </EntitlementGate>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {teams.map((team) => (
            <Link
              key={team.id}
              href={`/teams/${team.id}`}
              className="card group p-5 transition-shadow hover:shadow-popover"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
                    <UserSquare2 className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold text-ink group-hover:text-brand">
                      {team.name}
                    </h3>
                    <p className="text-[12px] text-faint">{team.code}</p>
                  </div>
                </div>
                <Badge tone="brand">{team.members_count}</Badge>
              </div>
              {team.description && (
                <p className="mt-3 line-clamp-2 text-[13px] leading-relaxed text-muted">
                  {team.description}
                </p>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[12px] text-faint">
                {team.department_name && <Badge>{team.department_name}</Badge>}
              </div>
              {team.lead_name && (
                <div className="mt-4 flex items-center gap-2 border-t border-line pt-3">
                  <Avatar name={team.lead_name} size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-medium text-ink">
                      {team.lead_name}
                    </p>
                    <p className="text-[11px] text-faint">Team lead</p>
                  </div>
                </div>
              )}
            </Link>
          ))}
        </div>
      )}

      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Create team"
        description="Set the lead and department â€” members join next."
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
              {formError}
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Name"
              name="name"
              required
              placeholder="Platform Squad"
            />
            <Input label="Code" name="code" placeholder="PLAT" />
          </div>
          <Textarea
            label="Description"
            name="description"
            rows={3}
            placeholder="What does this team ship?"
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField
              label="Department"
              name="department_id"
              options={departments.map((d) => ({ value: d.id, label: d.name }))}
            />
            <SelectField label="Team lead" name="lead_id" options={leads} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Create team
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function SelectField({
  label,
  name,
  options,
}: {
  label: string;
  name: string;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block text-[13px] font-medium text-muted">
      {label}
      <select
        name={name}
        className="mt-1.5 h-9 w-full rounded-lg border border-line bg-elevated px-2.5 text-[13px] text-ink outline-none focus:border-brand"
      >
        <option value="">None</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
