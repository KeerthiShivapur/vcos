"use client";

import { Suspense, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { createTemplate } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { TagInput } from "@/components/knowledge/TagInput";
import { toastSuccess } from "@/components/ui/Toaster";

const TEMPLATE_KINDS = [
  "meeting_notes",
  "architecture",
  "project_plan",
  "release_plan",
  "incident_report",
  "research",
  "customer_proposal",
  "contract",
  "training",
  "onboarding",
  "other",
];

export default function NewTemplatePage() {
  return (
    <Suspense fallback={null}>
      <NewTemplateContent />
    </Suspense>
  );
}

function NewTemplateContent() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const template = await createTemplate({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        content: String(form.get("content") ?? "").trim() || undefined,
        kind: String(form.get("kind") ?? "other") || "other",
        category: String(form.get("category") ?? "") || undefined,
        tags,
      });
      toastSuccess("Template created");
      router.push(`/templates/${template.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to create template",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        breadcrumb="Templates"
        title="New template"
        description="Use placeholders like {{name}} so people can fill it in fast."
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
          placeholder="e.g. Meeting Notes Template"
        />
        <Textarea
          label="Description"
          name="description"
          rows={2}
          placeholder="One-line summary"
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Kind"
            name="kind"
            defaultValue="other"
            options={TEMPLATE_KINDS.map((k) => ({
              value: k,
              label: k.replace(/_/g, " "),
            }))}
          />
          <Input
            label="Category"
            name="category"
            placeholder="e.g. operations"
          />
        </div>
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
          <Textarea
            name="content"
            rows={14}
            placeholder="# Agenda\n- Topic 1\n- Topic 2"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Link href="/templates">
            <Button type="button" variant="ghost">
              Cancel
            </Button>
          </Link>
          <Button type="submit" loading={saving}>
            Create template
          </Button>
        </div>
      </form>
    </div>
  );
}
