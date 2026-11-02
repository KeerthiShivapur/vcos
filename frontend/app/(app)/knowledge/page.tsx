"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  FileText,
  FolderTree,
  Gavel,
  History,
  LayoutGrid,
  ListChecks,
  Search,
  Sparkles,
  Stamp,
  Trophy,
  X,
} from "lucide-react";

import {
  getKnowledgeAnalytics,
  getKnowledgeExperts,
  getKnowledgeRecommendations,
  getMyKnowledgeFavorites,
  getRecentKnowledge,
  knowledgeSearch,
} from "@/lib/api";
import type {
  KnowledgeAnalytics,
  KnowledgeExpert,
  KnowledgeRecentItem,
  KnowledgeRecommendation,
  KnowledgeSearchResponse,
} from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import {
  KnowledgeBadge,
  kindLabel,
} from "@/components/knowledge/KnowledgeBadge";
import { KindIcon } from "@/components/knowledge/KindIcon";
import { formatDate } from "@/lib/utils";

const KINDS = ["document", "wiki", "policy", "sop", "template", "decision"];

const KIND_ICONS: Record<
  string,
  React.ComponentType<{ className?: string }>
> = {
  document: FileText,
  wiki: BookOpen,
  policy: Gavel,
  sop: ListChecks,
  template: Stamp,
  decision: FolderTree,
};

export default function KnowledgeHubPage() {
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<string>("");
  const [data, setData] = useState<KnowledgeSearchResponse | null>(null);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);

  const [recommendations, setRecommendations] = useState<
    KnowledgeRecommendation[]
  >([]);
  const [recent, setRecent] = useState<KnowledgeRecentItem[]>([]);
  const [favorites, setFavorites] = useState<KnowledgeRecentItem[]>([]);
  const [experts, setExperts] = useState<KnowledgeExpert[]>([]);
  const [analytics, setAnalytics] = useState<KnowledgeAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [recs, recentList, favList, expertList, analyticsData] =
          await Promise.all([
            getKnowledgeRecommendations(6).catch(
              () => [] as KnowledgeRecommendation[],
            ),
            getRecentKnowledge(6).catch(() => [] as KnowledgeRecentItem[]),
            getMyKnowledgeFavorites().catch(() => [] as KnowledgeRecentItem[]),
            getKnowledgeExperts().catch(() => [] as KnowledgeExpert[]),
            getKnowledgeAnalytics().catch(() => null),
          ]);
        setRecommendations(recs);
        setRecent(recentList);
        setFavorites(favList);
        setExperts(experts);
        setAnalytics(analyticsData);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load knowledge",
        );
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function runSearch(event?: React.FormEvent) {
    event?.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setSearched(true);
    try {
      setData(
        await knowledgeSearch({
          q,
          kind: kind || undefined,
          mode: "hybrid",
        }),
      );
    } catch {
      setData(null);
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setQuery("");
    setData(null);
    setSearched(false);
  }

  const totals = analytics?.totals ?? {};

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Hub"
        description="The company's brain — documents, wiki, policies, SOPs, templates and decisions, all searchable."
      />

      {error ? (
        <ErrorState title="Could not load knowledge" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading knowledge" />
        </div>
      ) : (
        <>
          <form onSubmit={runSearch} className="relative max-w-2xl">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Semantic search — try “how do we onboard new hires?”"
              className="input py-3 pl-10 pr-24 text-sm"
            />
            <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
              {query && (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="p-1 text-faint hover:text-muted"
                  aria-label="Clear"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
              <button
                type="submit"
                className="rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
              >
                {searching ? "Searching…" : "Search"}
              </button>
            </div>
          </form>

          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setKind("")}
              className={`rounded-full px-3 py-1 text-[12px] font-medium ${
                !kind
                  ? "bg-brand text-white"
                  : "bg-canvas text-muted hover:bg-surface"
              }`}
            >
              All
            </button>
            {KINDS.map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-medium ${
                  kind === k
                    ? "bg-brand text-white"
                    : "bg-canvas text-muted hover:bg-surface"
                }`}
              >
                <KindIcon kind={k} className="h-3.5 w-3.5" />
                {kindLabel(k)}
              </button>
            ))}
          </div>

          {searched ? (
            <div>
              {searching ? (
                <div className="flex justify-center py-16">
                  <Spinner label="Searching knowledge" />
                </div>
              ) : !data || data.results.length === 0 ? (
                <EmptyState
                  icon={Search}
                  title={`No knowledge matches “${query}”`}
                  description="Try different keywords or remove the kind filter."
                />
              ) : (
                <div className="space-y-2">
                  <p className="text-[12px] text-faint">
                    {data.total} result{data.total === 1 ? "" : "s"} ·{" "}
                    {data.mode} mode · {data.took_ms} ms
                  </p>
                  {data.results.map((result) => (
                    <Link
                      key={`${result.kind}-${result.id}`}
                      href={result.url}
                      className="card block p-4 transition-shadow hover:shadow-popover"
                    >
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 text-faint">
                          <KindIcon kind={result.kind} className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="truncate font-medium text-ink">
                              {result.title}
                            </p>
                            <KnowledgeBadge
                              status={String(result.metadata.status ?? "")}
                              kind={result.kind}
                            />
                          </div>
                          {result.snippet && (
                            <p className="mt-0.5 line-clamp-2 text-[13px] text-muted">
                              {result.snippet}
                            </p>
                          )}
                          {result.matched_keywords.length > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {result.matched_keywords.slice(0, 5).map((kw) => (
                                <span
                                  key={kw}
                                  className="rounded bg-canvas px-1.5 py-0.5 text-[11px] text-muted"
                                >
                                  {kw}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <span className="shrink-0 text-[12px] font-medium text-faint">
                          {Math.round(result.score * 100)}%
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <StatCard
                  label="Total items"
                  value={analytics?.total_items ?? 0}
                  icon={FileText}
                />
                <StatCard
                  label="Relations"
                  value={analytics?.total_relations ?? 0}
                  icon={Sparkles}
                />
                <StatCard
                  label="Avg quality"
                  value={analytics?.avg_quality_score ?? 0}
                  icon={Trophy}
                />
                <StatCard
                  label="Projects covered"
                  value={analytics?.coverage?.projects_with_knowledge ?? 0}
                  icon={LayoutGrid}
                />
              </div>

              <div className="grid gap-6 lg:grid-cols-3">
                <div className="space-y-6 lg:col-span-2">
                  <Card
                    title="Recommended for you"
                    subtitle="Based on your favorites and their relations"
                  >
                    {recommendations.length === 0 ? (
                      <EmptyState
                        icon={Sparkles}
                        title="Nothing recommended yet"
                        description="Favorite an item to personalize your feed."
                      />
                    ) : (
                      <div className="space-y-2">
                        {recommendations.map((rec) => (
                          <Link
                            key={`${rec.kind}-${rec.id}`}
                            href={rec.url}
                            className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5 transition-colors hover:bg-surface"
                          >
                            <span className="text-faint">
                              <KindIcon kind={rec.kind} className="h-4 w-4" />
                            </span>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-[13px] font-medium text-ink">
                                {rec.title}
                              </p>
                              <p className="truncate text-[12px] text-faint">
                                {rec.reason}
                              </p>
                            </div>
                            <Badge
                              tone={
                                rec.status === "published"
                                  ? "success"
                                  : "neutral"
                              }
                            >
                              {rec.status}
                            </Badge>
                          </Link>
                        ))}
                      </div>
                    )}
                  </Card>

                  <Card title="Recently viewed" subtitle="Your knowledge trail">
                    {recent.length === 0 ? (
                      <EmptyState
                        icon={History}
                        title="Nothing viewed yet"
                        description="Open an item and it will show up here."
                      />
                    ) : (
                      <div className="space-y-2">
                        {recent.map((item) => (
                          <Link
                            key={`${item.kind}-${item.id}`}
                            href={item.url}
                            className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5 transition-colors hover:bg-surface"
                          >
                            <span className="text-faint">
                              <KindIcon kind={item.kind} className="h-4 w-4" />
                            </span>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-[13px] font-medium text-ink">
                                {item.title}
                              </p>
                              <p className="text-[12px] text-faint">
                                {kindLabel(item.kind)} · viewed{" "}
                                {formatDate(item.viewed_at)}
                              </p>
                            </div>
                          </Link>
                        ))}
                      </div>
                    )}
                  </Card>
                </div>

                <div className="space-y-6">
                  <Card title="Favorites" subtitle="Your bookmarks">
                    {favorites.length === 0 ? (
                      <EmptyState icon={History} title="No favorites yet" />
                    ) : (
                      <div className="space-y-2">
                        {favorites.map((item) => (
                          <Link
                            key={`${item.kind}-${item.id}`}
                            href={item.url}
                            className="block truncate rounded-lg border border-line px-3 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-surface"
                          >
                            {item.title}
                          </Link>
                        ))}
                      </div>
                    )}
                  </Card>

                  <Card
                    title="Knowledge experts"
                    subtitle="Most prolific authors"
                  >
                    {experts.length === 0 ? (
                      <EmptyState icon={Trophy} title="No experts yet" />
                    ) : (
                      <div className="space-y-2">
                        {experts.map((expert) => (
                          <div
                            key={expert.employee_id}
                            className="flex items-center justify-between gap-2"
                          >
                            <p className="truncate text-[13px] font-medium text-ink">
                              {expert.name}
                            </p>
                            <Badge tone="brand">{expert.documents_count}</Badge>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>

                  <Card
                    title="Knowledge by type"
                    subtitle="What lives in the org"
                  >
                    <div className="space-y-2">
                      {KINDS.map((k) => (
                        <div
                          key={k}
                          className="flex items-center justify-between"
                        >
                          <span className="flex items-center gap-2 text-[13px] text-muted">
                            {(() => {
                              const Icon = KIND_ICONS[k];
                              return <Icon className="h-4 w-4 text-faint" />;
                            })()}
                            {kindLabel(k)}
                          </span>
                          <span className="text-[13px] font-semibold text-ink">
                            {totals[k] ?? 0}
                          </span>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
