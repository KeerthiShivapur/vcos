"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Plus } from "lucide-react";

import { createDepartment, getOrganizationStructure, listDepartments } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import type { Department, OrganizationStructure } from "@/types";
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

export default function DepartmentsPage() {
  return (
    <Suspense fallback={null}>
      <DepartmentsContent />
    </Suspense>
  );
}

function DepartmentsContent() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.DEPARTMENT_MANAGE);

  const [departments, setDepartments] = useState<Department[]>([]);
  const [structure, setStructure] = useState<OrganizationStructure | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [depts, org] = await Promise.all([listDepartments(), getOrganizationStructure()]);
      setDepartments(depts);
      setStructure(org);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load departments");
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
      setFormError("Department name is required.");
      return;
    }
    setSaving(true);
    try {
      await createDepartment({
        name,
        code: String(form.get("code") ?? "").trim() || undefined,
        description: String(form.get("description") ?? "").trim() || undefined,
        parent_id: String(form.get("parent_id") ?? "") || undefined,
        head_id: String(form.get("head_id") ?? "") || undefined,
        location_id: String(form.get("location_id") ?? "") || undefined,
      });
      toastSuccess("Department created");
      setShowCreate(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create department");
    } finally {
      setSaving(false);
    }
  }

  const locations = structure?.locations ?? [];
  const heads = departments.flatMap((d) => (d.head_id ? [{ value: d.head_id, label: d.head_name ?? d.head_id }] : []));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Departments"
        description="The building blocks of the organization."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> Create department
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState title="Could not load departments" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading departments" /></div>
      ) : departments.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No departments yet"
          description="Create your first department to start structuring the organization."
          action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> Create department</Button> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {departments.map((department) => (
            <Link key={department.id} href={`/departments/${department.id}`} className="card group p-5 transition-shadow hover:shadow-popover">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold text-ink group-hover:text-brand">{department.name}</h3>
                    <p className="text-[12px] text-faint">{department.code}</p>
                  </div>
                </div>
                <Badge tone="brand">{department.members_count}</Badge>
              </div>
              {department.description && (
                <p className="mt-3 line-clamp-2 text-[13px] leading-relaxed text-muted">{department.description}</p>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[12px] text-faint">
                {department.parent_name && <Badge>{department.parent_name}</Badge>}
                {department.location_name && <Badge>{department.location_name}</Badge>}
                {department.teams_count > 0 && <Badge>{department.teams_count} teams</Badge>}
              </div>
              {department.head_name && (
                <div className="mt-4 flex items-center gap-2 border-t border-line pt-3">
                  <Avatar name={department.head_name} size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-medium text-ink">{department.head_name}</p>
                    <p className="text-[11px] text-faint">Department head</p>
                  </div>
                </div>
              )}
            </Link>
          ))}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create department" description="Define the structure â€” heads, parents, and locations.">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Name" name="name" required placeholder="Engineering" />
            <Input label="Code" name="code" placeholder="ENG" />
          </div>
          <Textarea label="Description" name="description" rows={3} placeholder="What does this department own?" />
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Parent department" name="parent_id" options={departments.map((d) => ({ value: d.id, label: d.name }))} />
            <SelectField label="Department head" name="head_id" options={heads} />
          </div>
          <SelectField label="Location" name="location_id" options={locations.map((l) => ({ value: l.id, label: l.name }))} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create department</Button>
          </div>
        </form>
      </Modal>
    </div>
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
