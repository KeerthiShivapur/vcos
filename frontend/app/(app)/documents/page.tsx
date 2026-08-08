"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { FileText, Plus } from "lucide-react";

import { listDocuments } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Document } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KnowledgeCard } from "@/components/knowledge/KnowledgeCard";

export default function DocumentsPage() {
  return (
    <Suspense fallback={null}>
      <DocumentsContent />
    </Suspense>
  );
}

function DocumentsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setDocuments(
        await listDocuments({
          status: status || undefined,
          category: category || undefined,
          search: search || undefined,
          limit: 200,
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load documents");
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
        title="Documents"
        description="The enterprise document management hub — policies, handbooks, playbooks and more."
        actions={
          canManage ? (
            <Link href="/documents/new">
              <Button size="sm"><Plus className="h-4 w-4" /> New document</Button>
            </Link>
          ) : undefined
        }
      />

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search documents…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="All statuses"
          options={[
            { value: "draft", label: "Draft" },
            { value: "in_review", label: "In review" },
            { value: "published", label: "Published" },
            { value: "archived", label: "Archived" },
          ]}
          className="w-44"
        />
        <Select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="All categories"
          options={[
            { value: "hr", label: "HR" },
            { value: "engineering", label: "Engineering" },
            { value: "sales", label: "Sales" },
            { value: "finance", label: "Finance" },
            { value: "operations", label: "Operations" },
            { value: "marketing", label: "Marketing" },
            { value: "security", label: "Security" },
            { value: "general", label: "General" },
          ]}
          className="w-44"
        />
      </div>

      {error ? (
        <ErrorState title="Could not load documents" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading documents" /></div>
      ) : documents.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Create your first document to start building the org's memory."
          action={canManage ? <Link href="/documents/new"><Button size="sm"><Plus className="h-4 w-4" /> New document</Button></Link> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {documents.map((doc) => (
            <KnowledgeCard key={doc.id} item={doc} href={`/documents/${doc.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}
