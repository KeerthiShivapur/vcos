"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { createWikiPage, getWikiTree, listProjects } from "@/lib/api";
import type { Project, WikiTreeNode } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { TagInput } from "@/components/knowledge/TagInput";
import { toastSuccess } from "@/components/ui/Toaster";

export default function NewWikiPage() {
  return (
    <Suspense fallback={null}>
      <NewWikiContent />
    </Suspense>
  );
}

function NewWikiContent() {
  const router = useRouter();
  const [tree, setTree] = useState<WikiTreeNode[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [treeData, projectList] = await Promise.all([
        getWikiTree().catch(() => [] as WikiTreeNode[]),
        listProjects().catch(() => [] as Project[]),
      ]);
      setTree(treeData);
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
      const page = await createWikiPage({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        content: String(form.get("content") ?? "").trim() || undefined,
        space: String(form.get("space") ?? "organization") || "organization",
        category: String(form.get("category") ?? "") || undefined,
        parent_id: String(form.get("parent_id") ?? "") || undefined,
        project_id: String(form.get("project_id") ?? "") || undefined,
        tags,
      });
      toastSuccess("Wiki page created");
      router.push(`/wiki/${page.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create page");
    } finally {
      setSaving(false);
    }
  }

  function flatten(
    nodes: WikiTreeNode[],
    prefix = "",
  ): { value: string; label: string }[] {
    return nodes.flatMap((node) => [
      { value: node.id, label: `${prefix}${node.title}` },
      ...flatten(node.children ?? [], `${prefix}${node.title} / `),
    ]);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        breadcrumb="Wiki"
        title="New page"
        description="Write it and place it in the tree."
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
          placeholder="e.g. Engineering Handbook"
        />
        <Textarea
          label="Description"
          name="description"
          rows={2}
          placeholder="One-line summary"
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Space"
            name="space"
            defaultValue="organization"
            options={[
              "organization",
              "department",
              "project",
              "team",
              "personal",
            ].map((s) => ({
              value: s,
              label: s[0].toUpperCase() + s.slice(1),
            }))}
          />
          <Select
            label="Parent page"
            name="parent_id"
            placeholder="Root level"
            options={flatten(tree)}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Category"
            name="category"
            placeholder="e.g. engineering"
          />
          <Select
            label="Project"
            name="project_id"
            options={projects.map((p) => ({ value: p.id, label: p.name }))}
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
            rows={12}
            placeholder="Write the page body…"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Link href="/wiki">
            <Button type="button" variant="ghost">
              Cancel
            </Button>
          </Link>
          <Button type="submit" loading={saving}>
            Create page
          </Button>
        </div>
      </form>
    </div>
  );
}
