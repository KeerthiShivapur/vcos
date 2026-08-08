"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { createDocument, listEmployees, listProjects } from "@/lib/api";
import type { EmployeeSummary, Project } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { TagInput } from "@/components/knowledge/TagInput";
import { toastSuccess } from "@/components/ui/Toaster";

export default function NewDocumentPage() {
  return (
    <Suspense fallback={null}>
      <NewDocumentContent />
    </Suspense>
  );
}

function NewDocumentContent() {
  const router = useRouter();
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [empList, projectList] = await Promise.all([
        listEmployees({ page_size: 200 }).catch(() => [] as EmployeeSummary[]),
        listProjects().catch(() => [] as Project[]),
      ]);
      setEmployees(empList);
      setProjects(projectList);
    })();
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    try {
      let tags: string[] | undefined;
      const rawTags = form.get("tags");
      if (rawTags) {
        try {
          tags = JSON.parse(String(rawTags));
        } catch {
          tags = undefined;
        }
      }
      const doc = await createDocument({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        content: String(form.get("content") ?? "").trim() || undefined,
        category: String(form.get("category") ?? "") || undefined,
        visibility: String(form.get("visibility") ?? "organization") || "organization",
        owner_id: String(form.get("owner_id") ?? "") || undefined,
        project_id: String(form.get("project_id") ?? "") || undefined,
        tags,
      });
      toastSuccess("Document created");
      router.push(`/documents/${doc.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create document");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        breadcrumb="Documents"
        title="New document"
        description="Write it, tag it, and send it through review when it's ready."
      />
      <form onSubmit={handleSubmit} className="card space-y-4 p-6">
        {error && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{error}</div>}
        <Input label="Title" name="title" required placeholder="e.g. Onboarding Handbook" />
        <Textarea label="Description" name="description" rows={2} placeholder="One-line summary" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Category"
            name="category"
            options={["", "hr", "engineering", "sales", "finance", "operations", "marketing", "security", "general"].map((c) => ({
              value: c,
              label: c ? c[0].toUpperCase() + c.slice(1) : "Uncategorized",
            }))}
          />
          <Select
            label="Visibility"
            name="visibility"
            defaultValue="organization"
            options={["organization", "department", "team", "private"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Owner" name="owner_id" options={employees.map((e) => ({ value: e.id, label: e.full_name }))} />
          <Select label="Project" name="project_id" options={projects.map((p) => ({ value: p.id, label: p.name }))} />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">Tags</label>
          <TagInput name="tags" />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">Content</label>
          <Textarea name="content" rows={12} placeholder="Write the body…" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Link href="/documents"><Button type="button" variant="ghost">Cancel</Button></Link>
          <Button type="submit" loading={saving}>Create document</Button>
        </div>
      </form>
    </div>
  );
}
