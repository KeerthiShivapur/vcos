"use client";

import {
  ArrowRight,
  BarChart3,
  Crown,
  GitBranch,
  Gavel,
  Loader2,
  RotateCcw,
  Scale,
  Send,
  ShieldCheck,
  Sparkles,
  UserX,
  Users,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { useAuth } from "@/hooks/useAuth";
import {
  askPeopleDecision,
  createPeopleDecision,
  getPeopleDecisionDetail,
  getPeopleDecisions,
  peopleDecisionLifecycle,
  peopleDecisionWhatIf,
  recordPeopleDecisionOutcome,
  type PeopleDecisionBrainResponse,
  type PeopleDecisionCandidate,
  type PeopleDecisionDetail,
  type PeopleDecisionRecord,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const LIFECYCLE_TONE: Record<string, "success" | "brand" | "warning" | "danger" | "neutral"> = {
  detected: "neutral",
  evaluated: "neutral",
  recommended: "brand",
  reviewed: "warning",
  approved: "success",
  rejected: "danger",
  executed: "success",
  verified: "success",
  outcome: "neutral",
} as const;

const ROLE_TONE: Record<string, "success" | "brand" | "warning" | "neutral"> = {
  recommended: "success",
  alternative: "warning",
  excluded: "neutral",
} as const;

const RISK_TONE: Record<string, "success" | "warning" | "danger"> = {
  low: "success",
  medium: "warning",
  high: "danger",
} as const;

const DECISION_TYPES = [
  "staffing",
  "ownership",
  "collaboration",
  "capacity",
  "expertise",
  "stakeholders",
  "team_composition",
  "succession",
  "capability_gap",
] as const;

const CAN_ACT: Record<string, string[]> = {
  detected: ["evaluate"],
  evaluated: ["recommend"],
  recommended: ["review"],
  reviewed: ["approve", "reject"],
  approved: ["execute", "reject"],
  rejected: ["reopen"],
  executed: ["verify"],
  verified: [],
};

const OUTCOME_ABLE = new Set(["approved", "executed", "verified", "rejected"]);

export default function PeopleDecisionsPage() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.EMPLOYEES_MANAGE);

  const [decisions, setDecisions] = useState<PeopleDecisionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<PeopleDecisionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [brain, setBrain] = useState<PeopleDecisionBrainResponse | null>(null);
  const [asking, setAsking] = useState(false);

  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    decision_type: "staffing",
    objective: "",
    requirements: "",
    context_type: "org",
  });

  const refresh = useCallback(async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setLoading(true);
    setError(null);
    try {
      const res = await getPeopleDecisions({ limit: 50 });
      setDecisions(res.decisions);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load people decisions");
    } finally {
      if (!opts.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function ask() {
    const q = question.trim();
    if (!q) return;
    setAsking(true);
    setError(null);
    try {
      const res = await askPeopleDecision(q);
      setBrain(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to answer the question");
    } finally {
      setAsking(false);
    }
  }

  async function create() {
    setCreating(true);
    setError(null);
    try {
      const requirements = form.requirements
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean);
      const created = await createPeopleDecision({
        decision_type: form.decision_type,
        objective: form.objective.trim(),
        requirements,
        context_type: form.context_type === "org" ? "org" : null,
      });
      setForm({ ...form, objective: "", requirements: "" });
      setDetail(created);
      await refresh({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the decision");
    } finally {
      setCreating(false);
    }
  }

  async function openDecision(id: string) {
    setError(null);
    setDetail(null);
    try {
      setDetail(await getPeopleDecisionDetail(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load decision detail");
    }
  }

  async function act(action: string) {
    if (!detail) return;
    try {
      const updated = await peopleDecisionLifecycle(detail.id, action);
      setDetail(updated);
      await refresh({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to transition the decision");
    }
  }

  async function recordOutcome(status: "successful" | "unsuccessful") {
    if (!detail) return;
    try {
      const updated = await recordPeopleDecisionOutcome(
        detail.id,
        status,
        status === "successful" ? "recorded as successful from the People Decision Center" : "recorded as unsuccessful from the People Decision Center"
      );
      setDetail(updated);
      await refresh({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record the outcome");
    }
  }

  async function simulate(personId: string) {
    if (!detail) return;
    try {
      const updated = await peopleDecisionWhatIf(detail.id, personId);
      setDetail({ ...(await getPeopleDecisionDetail(detail.id)) });
      setError(null);
      if (updated.verdict) setError(updated.verdict);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run the simulation");
    }
  }

  function CandidateRow({ candidate }: { candidate: PeopleDecisionCandidate }) {
    return (
      <li className="rounded-lg border border-line/70 bg-surface px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {candidate.role === "recommended" ? (
              <Crown className="h-3.5 w-3.5 text-brand" />
            ) : candidate.role === "excluded" ? (
              <UserX className="h-3.5 w-3.5 text-faint" />
            ) : (
              <Users className="h-3.5 w-3.5 text-ink" />
            )}
            <p className="text-[13px] font-medium text-ink">{candidate.person_label}</p>
            <Badge tone={ROLE_TONE[candidate.role] ?? "neutral"}>{candidate.role}</Badge>
          </div>
          <p className="text-[11px] text-faint">
            {(candidate.evidence as { matched?: { length?: number } } | null)?.matched?.length ??
              Object.keys(candidate.evidence ?? {}).length}{" "}
            evidence dimension(s)
          </p>
        </div>
        {candidate.rationale && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted">{candidate.rationale}</p>
        )}
        {candidate.trade_off && candidate.role === "alternative" && (
          <p className="mt-1 text-[11px] italic leading-relaxed text-faint">{candidate.trade_off}</p>
        )}
        {candidate.why_not && (
          <p className="mt-1 text-[11px] leading-relaxed text-faint">why not: {candidate.why_not}</p>
        )}
      </li>
    );
  }

  if (error && !decisions.length && !detail && !loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="People Decision Center"
          breadcrumb="Brain"
          description="Who can own, staff or lead what — recommended from evidence, decided by people. Every recommendation is explainable; nothing is automatic."
        />
        <ErrorState title="Could not load people decisions" message={error} />
      </div>
    );
  }

  const pending = decisions.filter(
    (d) => d.lifecycle === "recommended" || d.lifecycle === "reviewed"
  ).length;
  const decided = decisions.filter((d) => d.outcome?.status).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="People Decision Center"
        breadcrumb="Brain"
        description="Objectives become required capabilities, capabilities become people with evidence, people become recommendations — with alternatives, trade-offs, confidence and full provenance. High-impact decisions (hiring, promotion, termination, compensation, discipline) always stay under human governance."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Decisions" value={loading ? "…" : total} icon={Scale} />
        <StatCard label="Awaiting human review" value={loading ? "…" : pending} icon={Gavel} />
        <StatCard label="Outcomes recorded" value={loading ? "…" : decided} icon={BarChart3} />
        <StatCard label="Simulated runs bounded" value="20 cap" icon={RotateCcw} />
      </div>

      <Card
        title="Ask the brain"
        subtitle='"Who should own …?", "why not X?", "what if we assign Y …?" — answered live from evidence, never persisting.'
      >
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder='e.g. "who should own the kubernetes platform?"'
            className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
          />
          <Button size="sm" onClick={ask} disabled={asking || !question.trim()}>
            {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Ask
          </Button>
        </div>
        {brain && (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="brand">{brain.intent}</Badge>
              <Badge tone="neutral">{brain.kind}</Badge>
              <Badge
                tone={RISK_TONE[brain.decision_type === "capability_gap" ? "low" : "medium"] ?? "neutral"}
              >
                {brain.decision_type}
              </Badge>
              {brain.scope === "project" && <Badge tone="neutral">scoped</Badge>}
              {brain.context?.context_label && (
                <span className="text-[11px] text-faint">context: {brain.context.context_label}</span>
              )}
            </div>
            <p className="rounded-xl border border-brand/30 bg-brand/5 p-3 text-[12px] leading-relaxed text-ink">
              {brain.answer}
            </p>
            {brain.candidates.length > 0 && (
              <ul className="space-y-1.5">
                {brain.candidates.map((c) => (
                  <CandidateRow key={`${c.person_id}-${c.role}`} candidate={c} />
                ))}
              </ul>
            )}
            {brain.provenance && (
              <p className="rounded-xl border border-line/70 bg-surface p-3 text-[11px] leading-relaxed text-faint">
                <span className="font-semibold text-ink">Provenance</span> ·{" "}
                {((brain.provenance.chain as string[]) ?? []).join(" → ")}
                {brain.provenance.constraints ? (
                  <>
                    {" · "}
                    {((brain.provenance.constraints as string[]) ?? []).join("; ")}
                  </>
                ) : null}
              </p>
            )}
          </div>
        )}
      </Card>

      <Card title="Create a governed decision" subtitle="The evidence is reasoned over immediately; a human being decides afterwards.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <select
            value={form.decision_type}
            onChange={(e) => setForm({ ...form, decision_type: e.target.value })}
            className="rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
          >
            {DECISION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={form.objective}
            onChange={(e) => setForm({ ...form, objective: e.target.value })}
            placeholder="Objective — who should do what, why?"
            className="rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand sm:col-span-2"
          />
          <input
            value={form.requirements}
            onChange={(e) => setForm({ ...form, requirements: e.target.value })}
            placeholder="Required capabilities (comma separated)"
            className="rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
          />
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-[12px] text-muted">
            <input
              type="checkbox"
              checked={form.context_type !== "org"}
              onChange={(e) => setForm({ ...form, context_type: e.target.checked ? "" : "org" })}
              className="accent-brand"
            />
            Anchor to a specific scope context later (project scope requires governance access)
          </label>
          <Button size="sm" onClick={create} disabled={creating || !form.objective.trim()}>
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Reason now
          </Button>
        </div>
      </Card>

      <Card
        title={`Decisions · ${total}`}
        subtitle="Every recommendation names its evidence; every lifecycle transition is append-only audited."
      >
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading decisions
          </div>
        ) : decisions.length === 0 ? (
          <EmptyState
            icon={Scale}
            title="No decisions yet"
            description="Ask a question above or create a governed decision — evidence appears immediately; humans decide afterwards."
          />
        ) : (
          <ul className="space-y-2">
            {decisions.map((d) => (
              <li key={d.id} className="rounded-xl border border-line/70 bg-elevated p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button type="button" onClick={() => openDecision(d.id)} className="min-w-0 text-left">
                    <p className="text-[13px] font-medium text-ink hover:text-brand">{d.objective}</p>
                    <p className="truncate text-[11px] text-faint">
                      {d.decision_type} · {d.risk_tier} risk · {timeAgo(d.created_at)}
                      {d.context?.context_label ? ` · ${d.context.context_label}` : ""}
                    </p>
                  </button>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Badge tone={LIFECYCLE_TONE[d.lifecycle] ?? "neutral"}>{d.lifecycle}</Badge>
                    {d.recommended_person_label && (
                      <span className="text-[12px] font-semibold text-ink">
                        {d.recommended_person_label}
                      </span>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => openDecision(d.id)}>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {detail && detail.id === d.id && (
                  <div className="mt-3 space-y-3 border-t border-line/60 pt-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={RISK_TONE[detail.risk_tier] ?? "warning"}>{detail.risk_tier}</Badge>
                      {detail.recommended_person_label && (
                        <Badge tone="success">
                          <Crown className="mr-1 h-3 w-3" /> {detail.recommended_person_label} ·{" "}
                          {(detail.confidence ?? 0).toFixed(2)} confidence
                        </Badge>
                      )}
                      {detail.outcome?.status && <Badge tone="neutral">outcome: {detail.outcome.status}</Badge>}
                    </div>
                    <p className="rounded-xl border border-line/70 bg-surface p-3 text-[12px] leading-relaxed text-ink">
                      {detail.recommendation?.rationale ?? detail.rationale ?? "No recommendation recorded."}
                    </p>

                    {detail.candidates.length > 0 && (
                      <>
                        <p className="text-[12px] font-semibold text-ink">
                          Candidates · {detail.candidates.length}
                        </p>
                        <ul className="space-y-1.5">
                          {detail.candidates.map((c) => (
                            <CandidateRow key={`${c.person_id}-${c.role}`} candidate={c} />
                          ))}
                        </ul>
                      </>
                    )}

                    {detail.simulations.length > 0 && (
                      <>
                        <p className="text-[12px] font-semibold text-ink">
                          Bounded what-if runs · {detail.simulations.length}
                        </p>
                        <ul className="space-y-1.5">
                          {detail.simulations.slice(0, 5).map((s) => (
                            <li key={s.id} className="rounded-lg border border-line/70 bg-surface px-3 py-2 text-[11px] text-muted">
                              {s.person_label} · {s.verdict}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}

                    {detail.audit.length > 0 && (
                      <>
                        <p className="text-[12px] font-semibold text-ink">Governance trail</p>
                        <ol className="space-y-1">
                          {detail.audit.map((a, i) => (
                            <li key={i} className="flex items-center gap-2 text-[11px] text-faint">
                              <ShieldCheck className="h-3 w-3 shrink-0 text-brand" />
                              <span className="font-medium text-ink">{a.action}</span>
                              <span className="truncate">{a.note}</span>
                              <span className="shrink-0">{timeAgo(a.created_at)}</span>
                            </li>
                          ))}
                        </ol>
                      </>
                    )}

                    {detail.provenance && (
                      <p className="rounded-xl border border-line/70 bg-surface p-3 text-[11px] leading-relaxed text-faint">
                        <span className="font-semibold text-ink">Provenance</span> ·{" "}
                        {((detail.provenance.chain as string[]) ?? []).join(" → ")}
                        {detail.provenance.formula ? (
                          <>
                            {" · "}
                            {String(detail.provenance.formula)}
                          </>
                        ) : null}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-2">
                      {canManage &&
                        (CAN_ACT[detail.lifecycle] ?? []).map((action) => (
                          <Button key={action} size="sm" onClick={() => act(action)}>
                            {action}
                          </Button>
                        ))}
                      {canManage && OUTCOME_ABLE.has(detail.lifecycle) && !detail.outcome?.status && (
                        <>
                          <Button size="sm" onClick={() => recordOutcome("successful")}>
                            Record successful
                          </Button>
                          <Button size="sm" variant="danger" onClick={() => recordOutcome("unsuccessful")}>
                            Record unsuccessful
                          </Button>
                        </>
                      )}
                      {canManage && detail.simulations.length >= 20 && !detail.outcome?.status && (
                        <Badge tone="warning">simulation budget exhausted (20 runs)</Badge>
                      )}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {error && <p className="mt-2 rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger"> {error}</p>}
      </Card>
    </div>
  );
}