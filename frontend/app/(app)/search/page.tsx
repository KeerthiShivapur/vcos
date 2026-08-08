"use client";

import { useState } from "react";
import {
  Bookmark,
  Building2,
  Circle,
  FileText,
  Search,
  Shield,
  X,
  Zap,
} from "lucide-react";

import { search } from "@/lib/api";
import { SearchResponse } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";

function iconFor(type: string): React.ReactNode {
  switch (type) {
    case "user":
      return <Circle className="h-4 w-4" />;
    case "bookmark":
      return <Bookmark className="h-4 w-4" />;
    case "shortcut":
      return <Zap className="h-4 w-4" />;
    case "organization":
      return <Building2 className="h-4 w-4" />;
    case "role":
      return <Shield className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
}

export default function SearchPage() {
  const { organization } = useAuth();
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [searched, setSearched] = useState(false);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setSearched(true);
    setFailed(false);
    try {
      setData(await search(q));
    } catch {
      setData(null);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  function clear() {
    setQuery("");
    setData(null);
    setSearched(false);
    setFailed(false);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Search"
        description={`Search everything inside ${organization?.name ?? "your company"}.`}
      />

      <form onSubmit={handleSubmit} className="relative max-w-xl">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
        <input
          autoFocus
          type="search"
          placeholder="Search people, notes, bookmarks, roles, audit logs..."
          className="input py-3 pl-10 pr-10 text-sm"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {query && (
          <button
            type="button"
            onClick={clear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-faint hover:text-muted"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </form>

      {loading ? (
        <div className="flex justify-center py-24"><Spinner label="Searching" /></div>
      ) : failed ? (
        <EmptyState title="Search failed" description="Something went wrong. Please try again." />
      ) : searched && (!data || data.results.length === 0) ? (
        <EmptyState
          title={`No results for “${query}”`}
          description="Try a different keyword — search covers users, workspace items, roles, and audit logs."
        />
      ) : data && data.results.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[12px] text-faint">
            {data.total} result{data.total === 1 ? "" : "s"} for “{data.query}” · {data.took_ms} ms
          </p>
          {data.results.map((result) => (
            <ResultRow key={`${result.type}-${result.id}`} result={result} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ResultRow({ result }: { result: SearchResponse["results"][number] }) {
  const kindLabel = (result.metadata?.kind as string | undefined) ?? result.type.replace(/_/g, " ");

  if (result.type === "user") {
    return (
      <Card className="flex items-center gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-[13px] font-semibold text-white">
          {result.title.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-ink">{result.title}</p>
          {result.subtitle ? <p className="truncate text-[13px] text-muted">{result.subtitle}</p> : null}
        </div>
        {result.metadata?.is_admin ? <Badge tone="brand">Admin</Badge> : <Badge tone="neutral">Member</Badge>}
      </Card>
    );
  }

  return (
    <Card className="flex items-start gap-3 p-4">
      <span className="mt-0.5 text-faint">{iconFor(result.type)}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate font-medium text-ink">{result.title}</p>
          <Badge tone="neutral">{kindLabel}</Badge>
        </div>
        {result.subtitle ? <p className="mt-0.5 truncate text-[13px] text-muted">{result.subtitle}</p> : null}
        {result.snippet ? <p className="mt-0.5 line-clamp-2 text-[13px] text-muted">{result.snippet}</p> : null}
      </div>
      <span className="shrink-0 text-[12px] text-faint">
        {formatDate(String(result.metadata?.created_at ?? ""))}
      </span>
    </Card>
  );
}
