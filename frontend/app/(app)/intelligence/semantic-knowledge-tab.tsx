"use client";

import { useState } from "react";
import { FileSearch, ScanSearch, Send } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { brainKnowledgeSearch } from "@/lib/api";
import type {
  BrainKnowledgeSearchResponse,
  BrainKnowledgeSearchResult,
} from "@/types";

const KIND_OPTIONS = ["document", "wiki", "policy", "sop", "template"] as const;

function scoreTone(score: number): "brand" | "success" | "neutral" {
  if (score >= 0.5) return "success";
  if (score >= 0.25) return "brand";
  return "neutral";
}

export function SemanticKnowledgeTab() {
  const [question, setQuestion] = useState("");
  const [kinds, setKinds] = useState<string[]>([...KIND_OPTIONS]);
  const [response, setResponse] = useState<BrainKnowledgeSearchResponse | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleKind = (kind: string) => {
    setKinds((current) =>
      current.includes(kind)
        ? current.filter((k) => k !== kind)
        : [...current, kind],
    );
  };

  const search = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await brainKnowledgeSearch({
        question: question.trim(),
        kinds: kinds.length ? kinds : null,
      });
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Knowledge search failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card
        title="Semantic knowledge search"
        subtitle="Hybrid retrieval over indexed documents, wikis, policies, SOPs and templates — bounded by your governance access"
      >
        <div className="space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void search();
            }}
            placeholder="e.g. what does the refund approval workflow require?"
            rows={2}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand"
          />
          <div className="flex flex-wrap items-center gap-2">
            {KIND_OPTIONS.map((kind) => (
              <button
                key={kind}
                onClick={() => toggleKind(kind)}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  kinds.includes(kind)
                    ? "border-brand bg-brand-soft text-brand"
                    : "border-line bg-surface text-muted hover:text-ink"
                }`}
              >
                {kind}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={search} disabled={busy || !question.trim()}>
              {busy ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
              ) : (
                <Send className="h-4 w-4" />
              )}{" "}
              Search knowledge
            </Button>
            <span className="ml-auto text-xs text-faint">
              retrieval_score is a ranking signal, never a claim confidence
            </span>
          </div>
          {notice && <p className="text-[13px] text-success">{notice}</p>}
          {error && <p className="text-[13px] text-danger">{error}</p>}
        </div>
      </Card>

      {response && (
        <Card
          title="Results"
          subtitle={`${response.total} matched · ${response.provider ?? "no provider"} · limit ${response.limit}${response.truncated ? " · truncated" : ""}`}
          bodyClassName="p-0"
        >
          {response.results.length === 0 ? (
            <EmptyState
              icon={FileSearch}
              title="Nothing matched within your access"
              description="Retrieval is scoped: only published knowledge you are authorized to see is scored."
            />
          ) : (
            <div className="divide-y divide-line">
              {response.results.map((result) => (
                <KnowledgeResultRow
                  key={`${result.source_type}-${result.source_id}-${result.chunk_index}`}
                  result={result}
                />
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function KnowledgeResultRow({
  result,
}: {
  result: BrainKnowledgeSearchResult;
}) {
  return (
    <div className="px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge tone="brand">{result.source_type}</Badge>
            <span className="truncate text-sm font-semibold text-ink">
              {result.title}
            </span>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
            {result.snippet}
          </p>
        </div>
        <Badge tone={result.scope === "org" ? "success" : "warning"}>
          {result.scope === "org" ? "org-wide" : "project-scoped"}
        </Badge>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Badge tone={scoreTone(result.semantic_score)}>
          semantic {result.semantic_score.toFixed(3)}
        </Badge>
        <Badge tone={scoreTone(result.lexical_score)}>
          lexical {result.lexical_score.toFixed(3)}
        </Badge>
        <Badge tone="neutral">
          retrieval {result.retrieval_score.toFixed(3)}
        </Badge>
        {result.project_id && <Badge tone="neutral">project anchored</Badge>}
        {result.updated_at && (
          <span className="text-[11px] text-faint">
            updated {new Date(result.updated_at).toLocaleString()}
          </span>
        )}
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-faint">
        <a
          href={result.url}
          className="inline-flex items-center gap-1 text-brand hover:underline"
        >
          <ScanSearch className="h-3 w-3" /> {result.url}
        </a>
        <span>
          provider {result.provider} · source {result.source_id.slice(0, 8)}
        </span>
      </div>
    </div>
  );
}
