"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  GitCompareArrows,
  MessageSquareQuote,
  Search,
  ShieldCheck,
  ScrollText,
} from "lucide-react";

import {
  brainAnswer,
  brainContradictions,
  brainLearningFeed,
  brainProvenance,
  getCompanyDecisionQuality,
  integrityFindings,
  integrityRunScan,
  integrityStatus,
  listCompanyDecisions,
  type CompanyDecisionRow4H2,
  type DecisionContradiction,
  type IntegrityFinding,
  type IntegrityStatus,
  type ProvenanceChain,
} from "@/lib/api";
import type { BrainAnswer } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDate } from "@/lib/utils";

const TABS = [
  { id: "integrity", label: "Integrity", icon: ShieldCheck },
  { id: "contradictions", label: "Contradictions", icon: GitCompareArrows },
  { id: "provenance", label: "Provenance", icon: ScrollText },
  { id: "answers", label: "Evidence Answers", icon: MessageSquareQuote },
  { id: "ledger", label: "Decision Ledger", icon: Activity },
];

const SEVERITY_TONE: Record<
  string,
  "neutral" | "brand" | "success" | "warning" | "danger"
> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "brand",
  info: "neutral",
};

export default function TruthCenterPage() {
  return (
    <Suspense fallback={null}>
      <TruthCenterContent />
    </Suspense>
  );
}

function TruthCenterContent() {
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") || "integrity";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Truth Center"
        description="What VCOS believes, why it believes it, what contradicts it, and what is broken — all backed by real records."
      />
      <Tabs
        tabs={TABS}
        active={tab}
        onChange={(id) => router.push(`/truth-center?tab=${id}`)}
      />
      {tab === "integrity" && <IntegrityTab />}
      {tab === "contradictions" && <ContradictionsTab />}
      {tab === "provenance" && <ProvenanceTab />}
      {tab === "answers" && <AnswersTab />}
      {tab === "ledger" && <LedgerTab />}
    </div>
  );
}

function IntegrityTab() {
  const [status, setStatus] = useState<IntegrityStatus | null>(null);
  const [findings, setFindings] = useState<IntegrityFinding[] | null>(null);
  const [severity, setSeverity] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, f] = await Promise.all([
        integrityStatus(),
        integrityFindings({ severity: severity || undefined, limit: 200 }),
      ]);
      setStatus(s);
      setFindings(f);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load integrity data",
      );
    }
  }, [severity]);

  useEffect(() => {
    load();
  }, [load]);

  async function runScan() {
    setScanning(true);
    try {
      await integrityRunScan({});
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!status || !findings) return <Spinner label="Scanning company records" />;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total findings" value={status.total_findings} />
        <Stat
          label="Open"
          value={status.open_findings}
          tone={status.open_findings ? "warning" : "success"}
        />
        <Stat
          label="Critical"
          value={status.by_severity.critical ?? 0}
          tone={status.by_severity.critical ? "danger" : "neutral"}
        />
        <Stat
          label="Last scan"
          value={status.last_scan ? formatDate(status.last_scan) : "—"}
          small
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={runScan}
          disabled={scanning}
        >
          <Search className="h-4 w-4" /> {scanning ? "Scanning…" : "Run scan"}
        </Button>
        {["", "critical", "high", "medium", "low", "info"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setSeverity(s)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${severity === s ? "border-brand bg-brand-soft text-brand" : "border-line text-faint hover:text-muted"}`}
          >
            {s === "" ? "All severities" : s}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-faint">
          {status.coverage_note}
        </span>
      </div>

      {findings.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No integrity findings"
          description="The current scan found no structural, tenant, temporal, provenance, epistemic, governance, or operating-chain issues."
        />
      ) : (
        <div className="space-y-2">
          {findings.map((f) => (
            <div
              key={f.id}
              className="rounded-lg border border-line bg-surface p-4"
            >
              <button
                className="flex w-full items-start justify-between gap-3 text-left"
                onClick={() => setExpanded(expanded === f.id ? null : f.id)}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <Badge tone={SEVERITY_TONE[f.severity] ?? "neutral"}>
                      {f.severity}
                    </Badge>
                    <span className="text-[13px] font-semibold text-ink">
                      {f.title}
                    </span>
                  </div>
                  <p className="mt-1 text-[13px] text-muted">{f.description}</p>
                  <p className="mt-1 text-[11px] text-faint">
                    {f.finding_type} · {f.entity_type} · {f.source_subsystem} ·
                    detected {f.detected_at ? formatDate(f.detected_at) : "—"}
                  </p>
                </div>
                <Badge tone="neutral">{f.status}</Badge>
              </button>
              {expanded === f.id && (
                <div className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
                  <EvidenceBlock
                    title="Observed evidence"
                    data={f.observed_evidence}
                  />
                  <EvidenceBlock
                    title="Derived evidence"
                    data={f.derived_evidence}
                  />
                  <EvidenceBlock title="Provenance" data={f.provenance} />
                  <div className="text-[12px] text-muted">
                    <p className="mb-1 font-medium text-ink">
                      Epistemic classification
                    </p>
                    <Badge tone="brand">{f.epistemic_classification}</Badge>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ContradictionsTab() {
  const [rows, setRows] = useState<DecisionContradiction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("open");

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await brainContradictions({
        status: statusFilter || undefined,
        limit: 50,
      });
      setRows(data.contradictions);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load contradictions",
      );
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rows) return <Spinner label="Loading contradictions" />;

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {["open", "resolved", ""].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${statusFilter === s ? "border-brand bg-brand-soft text-brand" : "border-line text-faint hover:text-muted"}`}
          >
            {s === "" ? "All" : s}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <EmptyState
          icon={GitCompareArrows}
          title="No contradictions in this view"
          description="Contradictions appear when recorded evidence conflicts with a decision's expected outcome."
        />
      ) : (
        rows.map((c) => (
          <div
            key={c.id}
            className="rounded-lg border border-line bg-surface p-4"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[12px] text-faint">
                <Badge tone={c.status === "open" ? "warning" : "success"}>
                  {c.status}
                </Badge>
                <span>decision {c.decision_id}</span>
                <span>· {c.contradiction_key}</span>
              </div>
              <span className="text-[11px] text-faint">
                {c.created_at ? formatDate(c.created_at) : ""}
              </span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <SideBlock
                label="Side A — recorded"
                side={c.side_a_json}
                tone="brand"
              />
              <SideBlock
                label="Side B — conflicting"
                side={c.side_b_json}
                tone="warning"
              />
            </div>
            {c.lesson_memory_id && (
              <p className="mt-2 text-[11px] text-faint">
                linked lesson: {c.lesson_memory_id}
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function ProvenanceTab() {
  const [lessons, setLessons] = useState<Record<string, unknown>[] | null>(
    null,
  );
  const [chain, setChain] = useState<ProvenanceChain | null>(null);
  const [lessonId, setLessonId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadingChain, setLoadingChain] = useState(false);

  const loadFeed = useCallback(async () => {
    setError(null);
    try {
      const data = await brainLearningFeed({ limit: 40 });
      setLessons((data.lessons as Record<string, unknown>[]) ?? []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load learning feed",
      );
    }
  }, []);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  async function openChain(id: string) {
    setLoadingChain(true);
    setError(null);
    try {
      setChain(await brainProvenance(id));
    } catch (err) {
      setChain(null);
      setError(
        err instanceof Error ? err.message : "Unable to load provenance chain",
      );
    } finally {
      setLoadingChain(false);
    }
  }

  if (error && !chain) return <ErrorState message={error} onRetry={loadFeed} />;
  if (!lessons) return <Spinner label="Loading learning feed" />;

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          placeholder="Look up a lesson id…"
          value={lessonId}
          onChange={(e) => setLessonId(e.target.value)}
          onKeyDown={(e) =>
            e.key === "Enter" && lessonId && openChain(lessonId)
          }
        />
        <Button
          size="sm"
          variant="secondary"
          onClick={() => lessonId && openChain(lessonId)}
        >
          Trace
        </Button>
      </div>

      {chain ? (
        <div className="space-y-3 rounded-lg border border-line bg-surface p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              Why does VCOS believe this? —{" "}
              {String(chain.lesson.title ?? chain.lesson_id)}
            </h3>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setChain(null)}
            >
              Back to feed
            </Button>
          </div>
          <div className="grid gap-3">
            <ChainBlock title="Lesson" items={[chain.lesson]} />
            {chain.pattern && (
              <ChainBlock title="Source pattern" items={[chain.pattern]} />
            )}
            <ChainBlock title="Evidence" items={chain.evidence} />
            <ChainBlock title="Quality assessments" items={chain.assessments} />
            <ChainBlock title="Outcomes" items={chain.outcomes} />
            <ChainBlock title="Contradictions" items={chain.contradictions} />
          </div>
        </div>
      ) : loadingChain ? (
        <Spinner label="Tracing provenance" />
      ) : lessons.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No lessons recorded yet"
          description="As the company learns from outcomes, every lesson will be traceable to its evidence here."
        />
      ) : (
        <div className="space-y-2">
          {lessons.map((lesson) => {
            const id = String(lesson.id ?? "");
            return (
              <button
                key={id}
                onClick={() => openChain(id)}
                className="w-full rounded-lg border border-line bg-surface p-3 text-left hover:border-brand"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium text-ink">
                    {String(lesson.title ?? "(untitled lesson)")}
                  </span>
                  <Badge tone="neutral">
                    {String(lesson.kind ?? "lesson")}
                  </Badge>
                </div>
                <p className="mt-1 line-clamp-2 text-[12px] text-muted">
                  {String(lesson.lesson ?? "")}
                </p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AnswersTab() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<BrainAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function ask() {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await brainAnswer({ question: question.trim() }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to answer");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Textarea
          label="Ask a question about your company"
          placeholder="e.g. What is blocking the Apollo beta?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
        />
        <Button size="sm" onClick={ask} disabled={loading || !question.trim()}>
          {loading ? "Thinking…" : "Ask with evidence"}
        </Button>
      </div>

      {error && <ErrorState message={error} onRetry={ask} />}
      {loading && <Spinner label="Gathering evidence" />}

      {answer && (
        <div className="space-y-3 rounded-lg border border-line bg-surface p-4">
          {answer.summary && (
            <p className="text-[14px] leading-6 text-ink">
              {answer.summary}
              <Badge tone="neutral" className="ml-2">
                confidence {Math.round((answer.confidence ?? 0) * 100)}%
              </Badge>
            </p>
          )}
          {answer.claims?.map((claim, i) => (
            <div
              key={i}
              className="rounded-md border border-line bg-canvas p-3"
            >
              <p className="text-[13px] font-medium text-ink">{claim.claim}</p>
              {claim.evidence?.length ? (
                <ul className="mt-2 space-y-1">
                  {claim.evidence.map((ref, j) => (
                    <li
                      key={j}
                      className="flex items-center gap-2 text-[12px] text-muted"
                    >
                      <Badge tone="brand">{ref.type}</Badge>
                      {ref.url ? (
                        <a
                          className="text-brand hover:underline"
                          href={ref.url}
                        >
                          {ref.title}
                        </a>
                      ) : (
                        <span>{ref.title}</span>
                      )}
                      <span className="text-faint">#{ref.id}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[12px] text-faint">
                  No cited evidence for this claim.
                </p>
              )}
            </div>
          ))}
          <p className="text-[11px] text-faint">
            sources consulted: {answer.sources_consulted?.join(", ") || "—"}
          </p>
        </div>
      )}
    </div>
  );
}

function LedgerTab() {
  const [rows, setRows] = useState<CompanyDecisionRow4H2[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [quality, setQuality] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await listCompanyDecisions({ limit: 50 });
      setRows(data.decisions ?? []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load decision ledger",
      );
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function expand(row: CompanyDecisionRow4H2) {
    if (expanded === row.decision_id) {
      setExpanded(null);
      setQuality(null);
      return;
    }
    setExpanded(row.decision_id);
    setQuality(null);
    try {
      setQuality(await getCompanyDecisionQuality(row.decision_id));
    } catch {
      setQuality({
        note: "No quality snapshot recorded for this decision yet.",
      });
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rows) return <Spinner label="Loading decision ledger" />;

  return (
    <div className="space-y-2">
      {rows.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No governed decisions yet"
          description="Decisions recorded through the governance path appear here with their evidence and quality history."
        />
      ) : (
        rows.map((row) => (
          <div
            key={row.decision_id}
            className="rounded-lg border border-line bg-surface p-4"
          >
            <button className="w-full text-left" onClick={() => expand(row)}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  tone={
                    row.state === "approved"
                      ? "success"
                      : row.state === "declined"
                        ? "danger"
                        : "warning"
                  }
                >
                  {row.state}
                </Badge>
                <span className="text-[13px] font-semibold text-ink">
                  {row.title}
                </span>
                <span className="text-[11px] text-faint">
                  {row.kind} · {row.decision_id}
                </span>
                {typeof row.evidence_count === "number" && (
                  <span className="ml-auto text-[11px] text-faint">
                    {row.evidence_count} evidence
                  </span>
                )}
              </div>
              {row.rationale && (
                <p className="mt-1 text-[12px] text-muted">{row.rationale}</p>
              )}
              <p className="mt-1 text-[11px] text-faint">
                owner {String(row.owner_label ?? "—")} · approver{" "}
                {String(row.approver_label ?? "—")} ·{" "}
                {formatDate(String(row.approved_at ?? row.updated_at ?? ""))}
              </p>
            </button>
            {expanded === row.decision_id && (
              <div className="mt-3 border-t border-line pt-3">
                <p className="mb-2 text-[12px] font-medium text-ink">
                  Quality snapshots
                </p>
                {quality ? (
                  <pre className="max-h-64 overflow-auto rounded-md bg-canvas p-3 text-[11px] text-muted">
                    {JSON.stringify(quality, null, 2)}
                  </pre>
                ) : (
                  <Spinner label="Loading quality" />
                )}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
  small = false,
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "success" | "warning" | "danger";
  small?: boolean;
}) {
  const toneClass =
    tone === "danger"
      ? "text-danger"
      : tone === "warning"
        ? "text-warning"
        : tone === "success"
          ? "text-success"
          : "text-ink";
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <p className="text-[11px] uppercase tracking-wide text-faint">{label}</p>
      <p
        className={`mt-1 font-semibold ${toneClass} ${small ? "text-[13px]" : "text-xl"}`}
      >
        {value}
      </p>
    </div>
  );
}

function EvidenceBlock({
  title,
  data,
}: {
  title: string;
  data: Record<string, unknown>;
}) {
  const empty = !data || Object.keys(data).length === 0;
  return (
    <div>
      <p className="mb-1 text-[12px] font-medium text-ink">{title}</p>
      {empty ? (
        <p className="text-[12px] text-faint">—</p>
      ) : (
        <pre className="max-h-40 overflow-auto rounded-md bg-canvas p-2 text-[11px] text-muted">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function SideBlock({
  label,
  side,
  tone,
}: {
  label: string;
  side: { claims?: string[]; evidence?: string[]; at?: string };
  tone: "brand" | "warning";
}) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <Badge tone={tone}>{label}</Badge>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-[12px] text-ink">
        {(side?.claims ?? []).map((claim, i) => (
          <li key={i}>{claim}</li>
        ))}
      </ul>
      {(side?.evidence ?? []).length > 0 && (
        <p className="mt-2 text-[11px] text-faint">
          evidence: {(side?.evidence ?? []).join("; ")}
        </p>
      )}
      {side?.at && <p className="text-[11px] text-faint">at {side.at}</p>}
    </div>
  );
}

function ChainBlock({
  title,
  items,
}: {
  title: string;
  items: Record<string, unknown>[];
}) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-1 text-[12px] font-medium text-ink">{title}</p>
      <div className="space-y-1">
        {items.map((item, i) => (
          <pre
            key={i}
            className="max-h-40 overflow-auto rounded-md bg-canvas p-2 text-[11px] text-muted"
          >
            {JSON.stringify(item, null, 2)}
          </pre>
        ))}
      </div>
    </div>
  );
}
