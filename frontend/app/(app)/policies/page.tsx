"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Gavel, Plus } from "lucide-react";

import { listOverduePolicies, listPolicies } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Policy } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KnowledgeCard } from "@/components/knowledge/KnowledgeCard";

const POLICY_CATEGORIES = [
  "general", "leave", "security", "travel", "expense", "remote_work", "conduct",
  "compliance", "privacy", "it", "access", "procurement", "quality", "safety", "other",
];

export default function PoliciesPage() {
  return (
    <Suspense fallback={null}>
      <PoliciesContent />
    </Suspense>
  );
}

function PoliciesContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [overdue, setOverdue] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [policyList, overdueList] = await Promise.all([
        listPolicies({ status: status || undefined, category: category || undefined, search: search || undefined, limit: 200 }),
        listOverduePolicies().catch(() => [] as Policy[]),
      ]);
      setPolicies(policyList);
      setOverdue(overdueList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load policies");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, category]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Policies"
        description="The rules everyone agreed to — with an approval workflow and review calendar."
        actions={canManage ? (
          <Link href="/policies/new"><Button size="sm"><Plus className="h-4 w-4" /> New policy</Button></Link>
        ) : undefined}
      />

      {overdue.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 p-4">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-warning">
            <AlertTriangle className="h-4 w-4" /> {overdue.length} polic{overdue.length === 1 ? "y" : "ies"} past its review date
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {overdue.slice(0, 6).map((policy) => (
              <Link key={policy.id} href={`/policies/${policy.id}`} className="rounded-md bg-white/60 px-2.5 py-1 text-[12px] font-medium text-ink hover:bg-white">
                {policy.title}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search policies…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="All statuses"
          options={["draft", "in_review", "approved", "published", "archived"].map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1).replace(/_/g, " ") }))}
          className="w-40"
        />
        <Select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="All categories"
          options={POLICY_CATEGORIES.map((c) => ({ value: c, label: c.replace(/_/g, " ") }))}
          className="w-44"
        />
      </div>

      {error ? (
        <ErrorState title="Could not load policies" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading policies" /></div>
      ) : policies.length === 0 ? (
        <EmptyState
          icon={Gavel}
          title="No policies yet"
          description="Write the policies that keep the company honest."
          action={canManage ? <Link href="/policies/new"><Button size="sm"><Plus className="h-4 w-4" /> New policy</Button></Link> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {policies.map((policy) => (
            <KnowledgeCard key={policy.id} item={policy} href={`/policies/${policy.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}
