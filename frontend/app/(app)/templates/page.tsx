"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Stamp } from "lucide-react";

import { listMostUsedTemplates, listTemplates } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Template } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KnowledgeCard } from "@/components/knowledge/KnowledgeCard";

const TEMPLATE_KINDS = [
  "meeting_notes", "architecture", "project_plan", "release_plan", "incident_report",
  "research", "customer_proposal", "contract", "training", "onboarding", "other",
];

export default function TemplatesPage() {
  return (
    <Suspense fallback={null}>
      <TemplatesContent />
    </Suspense>
  );
}

function TemplatesContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [mostUsed, setMostUsed] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState("");
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [templateList, usedList] = await Promise.all([
        listTemplates({ kind: kindFilter || undefined, search: search || undefined, limit: 200 }),
        listMostUsedTemplates().catch(() => [] as Template[]),
      ]);
      setTemplates(templateList);
      setMostUsed(usedList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load templates");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kindFilter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Templates"
        description="Reusable starting points for recurring work."
        actions={canManage ? (
          <Link href="/templates/new"><Button size="sm"><Plus className="h-4 w-4" /> New template</Button></Link>
        ) : undefined}
      />

      {mostUsed.length > 0 && (
        <div className="rounded-lg border border-brand/20 bg-brand-soft/40 p-4">
          <p className="text-[13px] font-semibold text-brand">Most used</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {mostUsed.slice(0, 5).map((template) => (
              <Link key={template.id} href={`/templates/${template.id}`} className="rounded-md bg-white/70 px-2.5 py-1 text-[12px] font-medium text-ink hover:bg-white">
                {template.title} · {template.usage_count}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search templates…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          placeholder="All kinds"
          options={TEMPLATE_KINDS.map((k) => ({ value: k, label: k.replace(/_/g, " ") }))}
          className="w-44"
        />
      </div>

      {error ? (
        <ErrorState title="Could not load templates" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading templates" /></div>
      ) : templates.length === 0 ? (
        <EmptyState
          icon={Stamp}
          title="No templates yet"
          description="Create templates for the work you repeat."
          action={canManage ? <Link href="/templates/new"><Button size="sm"><Plus className="h-4 w-4" /> New template</Button></Link> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {templates.map((template) => (
            <KnowledgeCard key={template.id} item={template} href={`/templates/${template.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}
