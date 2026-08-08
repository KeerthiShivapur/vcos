"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { ListChecks, Plus } from "lucide-react";

import { listSops } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { SOP } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KnowledgeCard } from "@/components/knowledge/KnowledgeCard";

export default function SopsPage() {
  return (
    <Suspense fallback={null}>
      <SopsContent />
    </Suspense>
  );
}

function SopsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);
  const [sops, setSops] = useState<SOP[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setSops(
        await listSops({ status: status || undefined, search: search || undefined, limit: 200 })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load SOPs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Standard Operating Procedures"
        description="Step-by-step playbooks for repeatable work."
        actions={canManage ? (
          <Link href="/sops/new"><Button size="sm"><Plus className="h-4 w-4" /> New SOP</Button></Link>
        ) : undefined}
      />

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search SOPs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="All statuses"
          options={["draft", "published", "archived"].map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))}
          className="w-40"
        />
      </div>

      {error ? (
        <ErrorState title="Could not load SOPs" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading SOPs" /></div>
      ) : sops.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No SOPs yet"
          description="Capture your repeatable processes as checklists."
          action={canManage ? <Link href="/sops/new"><Button size="sm"><Plus className="h-4 w-4" /> New SOP</Button></Link> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sops.map((sop) => (
            <KnowledgeCard key={sop.id} item={sop} href={`/sops/${sop.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}
