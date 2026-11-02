"use client";

import { Suspense, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { GripVertical, Plus, Trash2 } from "lucide-react";

import { createSop } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { TagInput } from "@/components/knowledge/TagInput";
import { toastSuccess } from "@/components/ui/Toaster";

interface StepDraft {
  title: string;
  instruction: string;
  is_checklist: boolean;
}

export default function NewSopPage() {
  return (
    <Suspense fallback={null}>
      <NewSopContent />
    </Suspense>
  );
}

function NewSopContent() {
  const router = useRouter();
  const [steps, setSteps] = useState<StepDraft[]>([
    { title: "", instruction: "", is_checklist: true },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateStep(index: number, patch: Partial<StepDraft>) {
    setSteps((prev) =>
      prev.map((step, i) => (i === index ? { ...step, ...patch } : step)),
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setError("Title is required.");
      return;
    }
    const cleanSteps = steps
      .map((step, i) => ({
        title: step.title.trim(),
        instruction: step.instruction.trim() || undefined,
        is_checklist: step.is_checklist,
        sort_order: i,
      }))
      .filter((step) => step.title.length > 0);

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
      const sop = await createSop({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        content: String(form.get("content") ?? "").trim() || undefined,
        steps: cleanSteps,
        tags,
      });
      toastSuccess("SOP created");
      router.push(`/sops/${sop.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create SOP");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        breadcrumb="SOPs"
        title="New SOP"
        description="Break the process into ordered, checkable steps."
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
          placeholder="e.g. New Hire Laptop Setup"
        />
        <Textarea
          label="Description"
          name="description"
          rows={2}
          placeholder="One-line summary"
        />
        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">
            Tags
          </label>
          <TagInput name="tags" />
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[13px] font-medium text-ink">Steps</label>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() =>
                setSteps((prev) => [
                  ...prev,
                  { title: "", instruction: "", is_checklist: true },
                ])
              }
            >
              <Plus className="h-4 w-4" /> Add step
            </Button>
          </div>
          <div className="space-y-2">
            {steps.map((step, index) => (
              <div
                key={index}
                className="rounded-lg border border-line bg-canvas p-3"
              >
                <div className="flex items-center gap-2">
                  <GripVertical className="h-4 w-4 shrink-0 text-faint" />
                  <span className="w-6 shrink-0 text-[12px] font-bold text-faint">
                    {index + 1}.
                  </span>
                  <Input
                    placeholder="Step title"
                    value={step.title}
                    onChange={(e) =>
                      updateStep(index, { title: e.target.value })
                    }
                    className="text-sm"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setSteps((prev) => prev.filter((_, i) => i !== index))
                    }
                    className="shrink-0 p-1 text-faint hover:text-danger"
                    aria-label="Remove step"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-2 flex items-start gap-2 pl-12">
                  <Input
                    placeholder="Instruction (optional)"
                    value={step.instruction}
                    onChange={(e) =>
                      updateStep(index, { instruction: e.target.value })
                    }
                    className="text-sm"
                  />
                  <label className="flex shrink-0 items-center gap-1.5 text-[12px] text-muted">
                    <input
                      type="checkbox"
                      checked={step.is_checklist}
                      onChange={(e) =>
                        updateStep(index, { is_checklist: e.target.checked })
                      }
                      className="accent-brand"
                    />
                    Checklist
                  </label>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">
            Overview
          </label>
          <Textarea
            name="content"
            rows={5}
            placeholder="Brief description of when and how to use this SOP…"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Link href="/sops">
            <Button type="button" variant="ghost">
              Cancel
            </Button>
          </Link>
          <Button type="submit" loading={saving}>
            Create SOP
          </Button>
        </div>
      </form>
    </div>
  );
}
