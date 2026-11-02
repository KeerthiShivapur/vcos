"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { createPolicy, listEmployees } from "@/lib/api";
import type { EmployeeSummary } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { TagInput } from "@/components/knowledge/TagInput";
import { toastSuccess } from "@/components/ui/Toaster";

const POLICY_CATEGORIES = [
  "general",
  "leave",
  "security",
  "travel",
  "expense",
  "remote_work",
  "conduct",
  "compliance",
  "privacy",
  "it",
  "access",
  "procurement",
  "quality",
  "safety",
  "other",
];

export default function NewPolicyPage() {
  return (
    <Suspense fallback={null}>
      <NewPolicyContent />
    </Suspense>
  );
}

function NewPolicyContent() {
  const router = useRouter();
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listEmployees({ page_size: 200 })
      .then(setEmployees)
      .catch(() => setEmployees([]));
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
      const policy = await createPolicy({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        content: String(form.get("content") ?? "").trim() || undefined,
        category:
          String(form.get("category") ?? "general")
            .trim()
            .toLowerCase()
            .replace(/\s+/g, "_") || "general",
        owner_id: String(form.get("owner_id") ?? "") || undefined,
        approver_id: String(form.get("approver_id") ?? "") || undefined,
        effective_date: String(form.get("effective_date") ?? "") || undefined,
        review_date: String(form.get("review_date") ?? "") || undefined,
        tags,
      });
      toastSuccess("Policy created");
      router.push(`/policies/${policy.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create policy");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        breadcrumb="Policies"
        title="New policy"
        description="Set a review date so the policy never goes stale."
      />
      <form onSubmit={handleSubmit} className="card space-y-4 p-6">
        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
            {error}
          </div>
        )}
        <Input
          label="Title"
          name="title"
          required
          placeholder="e.g. Remote Work Policy"
        />
        <Textarea
          label="Description"
          name="description"
          rows={2}
          placeholder="One-line summary"
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Category"
            name="category"
            defaultValue="general"
            options={POLICY_CATEGORIES.map((c) => ({
              value: c,
              label: c.replace(/_/g, " "),
            }))}
          />
          <Input label="Effective date" name="effective_date" type="date" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Owner"
            name="owner_id"
            options={employees.map((e) => ({
              value: e.id,
              label: e.full_name,
            }))}
          />
          <Select
            label="Approver"
            name="approver_id"
            options={employees.map((e) => ({
              value: e.id,
              label: e.full_name,
            }))}
          />
        </div>
        <Input
          label="Review date"
          name="review_date"
          type="date"
          hint="Policies past this date appear as overdue."
        />
        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">
            Tags
          </label>
          <TagInput name="tags" />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">
            Content
          </label>
          <Textarea name="content" rows={12} placeholder="Write the policy…" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Link href="/policies">
            <Button type="button" variant="ghost">
              Cancel
            </Button>
          </Link>
          <Button type="submit" loading={saving}>
            Create policy
          </Button>
        </div>
      </form>
    </div>
  );
}
