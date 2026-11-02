"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Search,
  X,
  ChevronRight,
  User,
  Building2,
  FolderKanban,
  CheckSquare2,
  CalendarDays,
  FileText,
  Handshake,
  Network,
  Scale,
  Target,
  Zap,
  Clock,
  MessageSquare,
  BookOpen,
  Shield,
  Sparkles,
  Command as CommandIcon,
  Keyboard,
  ArrowRight,
  Bookmark,
  Megaphone,
  Users,
} from "lucide-react";

import { universalSearch } from "@/lib/api";
import { UniversalSearchResult } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";

const TYPE_ICONS: Record<
  string,
  React.ComponentType<{ className?: string }>
> = {
  user: User,
  project: FolderKanban,
  task: CheckSquare2,
  meeting: CalendarDays,
  document: FileText,
  customer: Handshake,
  organization: Building2,
  role: Shield,
  decision: Scale,
  commitment: Target,
  action: Zap,
  process: Zap,
  message: MessageSquare,
  knowledge: BookOpen,
  note: FileText,
  bookmark: Bookmark,
  shortcut: Zap,
  announcement: Megaphone,
  community: Users,
  goal: Target,
};

const TYPE_LABELS: Record<string, string> = {
  user: "Person",
  project: "Project",
  task: "Task",
  meeting: "Meeting",
  document: "Document",
  customer: "Customer",
  organization: "Organization",
  role: "Role",
  decision: "Decision",
  commitment: "Commitment",
  action: "Action",
  process: "Process",
  message: "Message",
  knowledge: "Knowledge",
  note: "Note",
  bookmark: "Bookmark",
  shortcut: "Shortcut",
  announcement: "Announcement",
  community: "Community",
  goal: "Goal",
};

export default function UniversalSearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { organization } = useAuth();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [data, setData] = useState<UniversalSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [total, setTotal] = useState(0);
  const [tookMs, setTookMs] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (searchParams.get("q")) {
      setQuery(searchParams.get("q")!);
      handleSearch(searchParams.get("q")!);
    }
  }, [searchParams.get("q")]);

  const handleSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setLoading(true);
    try {
      const result = await universalSearch({ query: trimmed, limit: 50 });
      setData(result.results);
      setTotal(result.total);
      setTookMs(result.took_ms);
      setSearched(true);
      setSelectedIndex(0);
    } catch {
      setData([]);
      setTotal(0);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (q) {
      router.push(`/search?q=${encodeURIComponent(q)}`);
      handleSearch(q);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, data.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && selectedIndex >= 0 && data[selectedIndex]) {
      e.preventDefault();
      const result = data[selectedIndex];
      if (result.deep_link) {
        router.push(result.deep_link);
      }
    } else if (e.key === "Escape") {
      setQuery("");
      setData([]);
      setSearched(false);
      inputRef.current?.blur();
    }
  };

  const clear = () => {
    setQuery("");
    setData([]);
    setSearched(false);
    setSelectedIndex(-1);
    router.push("/search");
    inputRef.current?.focus();
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <PageHeader
        title="Universal Search"
        description={`Search everything inside ${organization?.name ?? "your company"}. Press ⌘K to open from anywhere.`}
      />

      <form onSubmit={handleSubmit} className="relative max-w-3xl mx-auto">
        <div className="relative">
          <CommandIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <Keyboard className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <input
            ref={inputRef}
            autoFocus
            type="search"
            placeholder="Search people, projects, tasks, meetings, documents, decisions, commitments..."
            className="input py-3.5 pl-10 pr-10 text-base"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(-1);
            }}
            onKeyDown={handleKeyDown}
          />
          {query && (
            <button
              type="button"
              onClick={clear}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-faint hover:text-muted"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <p className="mt-2 text-center text-[12px] text-faint">
          ⌘K to open · ↑↓ to navigate · Enter to open · Esc to clear
        </p>
      </form>

      {loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Searching" />
        </div>
      ) : searched && (!data || data.length === 0) ? (
        <EmptyState
          title={`No results for "${query}"`}
          description="Try a different keyword — search covers people, projects, tasks, meetings, documents, decisions, commitments, and more."
        />
      ) : data && data.length > 0 ? (
        <div className="space-y-2" ref={resultsRef}>
          <p className="text-[12px] text-faint mx-auto max-w-3xl">
            {total} result{total === 1 ? "" : "s"} for &quot;{query}&quot; ·{" "}
            {tookMs} ms
          </p>
          {data.map((result, index) => (
            <UniversalSearchResultRow
              key={`${result.type}-${result.id}`}
              result={result}
              index={index}
              isSelected={index === selectedIndex}
              onSelect={() => router.push(result.deep_link)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-24 text-muted">
          <Search className="h-12 w-12 mx-auto mb-4 text-faint" />
          <p className="text-muted">
            Press ⌘K or start typing to search across your company
          </p>
          <p className="text-[12px] text-faint mt-2">
            Searches: People, Projects, Tasks, Meetings, Documents, Decisions,
            Commitments, Knowledge, Messages, and more.
          </p>
        </div>
      )}
    </div>
  );
}

function UniversalSearchResultRow({
  result,
  index,
  isSelected,
  onSelect,
}: {
  result: UniversalSearchResult;
  index: number;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const Icon = TYPE_ICONS[result.type] || FileText;
  const typeLabel = TYPE_LABELS[result.type] ?? result.type;

  return (
    <Card
      className={`flex items-center gap-3 p-3 transition-colors ${
        isSelected
          ? "bg-brand/5 border-brand ring-1 ring-brand"
          : "hover:bg-canvas/60"
      }`}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      tabIndex={0}
      role="option"
      aria-selected={isSelected}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate font-medium text-ink">{result.title}</p>
          <Badge tone="neutral" className="text-[11px]">
            {typeLabel}
          </Badge>
        </div>
        {result.subtitle && (
          <p className="truncate text-[12px] text-muted">{result.subtitle}</p>
        )}
        {result.description && (
          <p className="mt-0.5 line-clamp-2 text-[12px] text-muted">
            {result.description}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 text-[11px] text-faint">
        <span>
          {result.metadata?.created_at
            ? formatDate(result.metadata.created_at)
            : ""}
        </span>
        <ChevronRight className="h-3.5 w-3.5" />
      </div>
    </Card>
  );
}
