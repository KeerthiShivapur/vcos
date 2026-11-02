"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  FlaskConical,
  GitCompareArrows,
  HeartPulse,
  History,
  Lightbulb,
  Link2,
  ListChecks,
  Loader2,
  Scale,
  Send,
  ShieldAlert,
  Sparkles,
  Target,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { StatCard } from "@/components/ui/PageHeader";
import { useAuth } from "@/hooks/useAuth";
import {
  evaluateCompanyDecision,
  executeCompanyDecision,
  getCompanyCausalChain,
  getCompanyChanges,
  getCompanyDecisionAlternatives,
  getCompanyDecisionContradictions,
  getCompanyDecisionImpact,
  getCompanyDecisionPrediction,
  getCompanyDecisionPrecedents,
  getCompanyDecisionQuality,
  getCompanyDecisionWhyNot,
  getCompanyMemory,
  getCompanyNarrative,
  getCompanyOperatingHealth,
  getCompanyRecommendations,
  getCompanyState,
  getCompanyTemporalSeries,
  recommendCompanyDecision,
  recordCompanyDecision,
  recordCompanyOutcome,
  compareCompanyScenarios,
  listCompanyScenarios,
  rehearseCompanyScenario,
  runCompanyWhatHappensIf,
  deriveCompanyActionPlan,
  companyExecutionChain,
  getCompanyDecisionPerformance,
  getCompanyPerformanceCohort,
  compareCompanyDecisions,
  brainKnowledgeActionPropose,
  type CompanyActionPlanResponse,
  type CompanyActionPlanStep,
  type CompanyExecutionChainResponse,
  type CompanyPerformanceAssessment,
  type CompanyPerformanceCohortResponse,
  type CompanyPerformanceComparisonResponse,
  type CompanyCausalChainResponse,
  type CompanyChangesResponse,
  type CompanyDecisionRow,
  type CompanyHealthResponse,
  type CompanyMemoryResponse,
  type CompanyNarrativeResponse,
  type CompanyRecommendationsResponse,
  type CompanyScenarioCompareResponse,
  type CompanyScenarioHistoryResponse,
  type CompanyScenarioRehearseResponse,
  type CompanyStateResponse,
  type CompanyTemporalSeriesResponse,
  type CompanyWhatIfResponse,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const STATE_TONE: Record<
  string,
  "success" | "warning" | "danger" | "neutral" | "brand"
> = {
  healthy: "success",
  concerned: "warning",
  watch: "warning",
  at_risk: "danger",
  critical: "danger",
  excellent: "success",
} as const;

const CHANGE_TONE: Record<
  string,
  "brand" | "danger" | "warning" | "neutral" | "success"
> = {
  new_constraint: "danger",
  resolved_constraint: "success",
  declined: "danger",
  state_shift: "warning",
  improved: "success",
  no_window: "neutral",
} as const;

const SOURCE_TONE: Record<
  string,
  "brand" | "danger" | "warning" | "neutral" | "success"
> = {
  strategy: "brand",
  execution: "brand",
  capacity: "warning",
  coordination: "warning",
  customer: "danger",
  business: "brand",
  knowledge: "neutral",
} as const;

const HOP_KIND_TONE: Record<
  string,
  "brand" | "danger" | "warning" | "neutral" | "success"
> = {
  "capability->project": "warning",
  "capacity->project": "warning",
  "project->milestone": "brand",
  "project->customer": "danger",
  "milestone->customer": "danger",
  "decision->task": "brand",
  "task->execution": "neutral",
  "execution->outcome": "success",
  "dependency->project": "warning",
  "person->capability": "brand",
} as const;

function decisionKindFor(recommendation: {
  title: string;
  source: string;
  kind: string;
}): string {
  const lowered =
    `${recommendation.title} ${recommendation.source} ${recommendation.kind}`.toLowerCase();
  if (lowered.includes("hire")) return "hire";
  if (lowered.includes("delay")) return "delay_project";
  if (lowered.includes("realloc")) return "reallocate_capacity";
  if (lowered.includes("priorit")) return "change_priority";
  if (lowered.includes("conflict")) return "resolve_conflict";
  if (lowered.includes("coordination")) return "improve_coordination";
  if (lowered.includes("customer") || lowered.includes("commitment"))
    return "customer_mitigation";
  if (recommendation.source === "business") return "commercial_action";
  return "other";
}

function DecisionIntelPanel({
  data,
  busy,
}: {
  data: Record<string, unknown> | null;
  busy: boolean;
}) {
  if (busy) {
    return (
      <p className="mt-2 flex items-center gap-2 text-[11px] text-faint">
        <Loader2 className="h-3 w-3 animate-spin" /> Loading decision
        intelligence
      </p>
    );
  }
  if (!data) return null;
  const prediction = (data.prediction ?? {}) as Record<string, unknown>;
  const quality = (data.quality ?? {}) as Record<string, unknown>;
  const reconciliation = (prediction.reconciliation ?? {}) as Record<
    string,
    unknown
  >;
  const qualitySnapshot = (quality.latest ?? {}) as Record<string, unknown>;
  const snapshots = (quality.snapshots ?? []) as Record<string, unknown>[];
  const alternatives = ((
    data.alternatives as
      { alternatives?: Record<string, unknown>[] } | undefined
  )?.alternatives ?? []) as Record<string, unknown>[];
  const whyNot = ((
    data.whyNot as { why_not?: Record<string, unknown>[] } | undefined
  )?.why_not ?? []) as Record<string, unknown>[];
  const precedents = ((
    data.precedents as { precedents?: Record<string, unknown>[] } | undefined
  )?.precedents ?? []) as Record<string, unknown>[];
  const contradictions = ((
    data.contradictions as
      { contradictions?: Record<string, unknown>[] } | undefined
  )?.contradictions ?? []) as Record<string, unknown>[];
  const impact = (data.impact ?? {}) as Record<string, unknown>;

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-line/60 bg-surface p-2.5 text-[11px]">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="brand">prediction</Badge>
        {reconciliation.aligned != null && (
          <Badge tone={reconciliation.aligned ? "success" : "danger"}>
            {reconciliation.aligned ? "aligned" : "misaligned"}
          </Badge>
        )}
        {prediction.not_yet_measurable === true && (
          <Badge tone="neutral">not yet measurable</Badge>
        )}
        <span className="text-faint">
          {prediction.band != null
            ? `band ${String(prediction.band)}`
            : "band not recorded"}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="brand">quality</Badge>
        {qualitySnapshot.risk_band != null && (
          <Badge tone="neutral">{String(qualitySnapshot.risk_band)}</Badge>
        )}
        {qualitySnapshot.decision_count != null && (
          <span className="text-faint">
            decisions {String(qualitySnapshot.decision_count)}
          </span>
        )}
        <span className="text-faint">
          stages{" "}
          {snapshots
            .map((s) => String((s as Record<string, unknown>).stage))
            .join(" → ") || "—"}
        </span>
      </div>

      {(alternatives.length > 0 || whyNot.length > 0) && (
        <div className="space-y-1.5">
          <p className="flex flex-wrap items-center gap-1.5">
            <Badge tone="brand">alternatives</Badge>
            <Badge tone="neutral">{alternatives.length}</Badge>
          </p>
          <ul className="space-y-1">
            {alternatives.map((alt, idx) => {
              const a = (alt ?? {}) as Record<string, unknown>;
              return (
                <li key={idx} className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={a.chosen ? "success" : "neutral"}>
                    {a.chosen ? "chosen" : "rejected"}
                  </Badge>
                  <span className="text-ink">
                    {String(a.label ?? a.alternative_key ?? "—")}
                  </span>
                  {Boolean(a.why_chosen) && (
                    <span className="text-faint">· {String(a.why_chosen)}</span>
                  )}
                </li>
              );
            })}
            {whyNot.map((w, idx) => {
              const entry = (w ?? {}) as Record<string, unknown>;
              return (
                <li key={`w${idx}`} className="text-faint">
                  {String(entry.alternative_key ?? "—")} —{" "}
                  {String(entry.why_not ?? "—")}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {(precedents.length > 0 || contradictions.length > 0) && (
        <div className="space-y-1.5">
          <p className="flex flex-wrap items-center gap-1.5">
            <Badge tone="brand">precedents</Badge>
            <Badge tone={contradictions.length > 0 ? "danger" : "neutral"}>
              {contradictions.length > 0 ? "conflicting" : "consistent"}
            </Badge>
          </p>
          {precedents.length > 0 && (
            <ul className="space-y-1">
              {precedents.slice(0, 3).map((p, idx) => {
                const entry = (p ?? {}) as Record<string, unknown>;
                return (
                  <li key={idx} className="text-faint">
                    {String(entry.title ?? entry.decision_id ?? "—")}
                  </li>
                );
              })}
            </ul>
          )}
          {contradictions.slice(0, 2).map((c, idx) => {
            const entry = (c ?? {}) as Record<string, unknown>;
            return (
              <p key={idx} className="flex items-start gap-1.5 text-faint">
                <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0 text-danger" />
                {String(
                  entry.summary ?? entry.reason ?? "evidence is conflicting",
                )}
              </p>
            );
          })}
        </div>
      )}

      {impact && (impact.observed ?? impact.direct ?? impact.total) != null && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="brand">impact</Badge>
          <span className="text-faint">
            observed {String(impact.observed ?? 0)}
          </span>
          <span className="text-faint">
            · direct {String(impact.direct ?? 0)}
          </span>
          <span className="text-faint">
            · indepth {String(impact.total ?? 0)}
          </span>
        </div>
      )}
    </div>
  );
}

const TRUTH_TONE: Record<string, "success" | "brand" | "warning" | "neutral"> =
  {
    recorded: "success",
    derived: "brand",
    unknown: "warning",
  } as const;

const ATTRIBUTION_TONE: Record<string, "success" | "brand" | "neutral"> = {
  SUPPORTED: "success",
  ASSOCIATED: "brand",
  UNKNOWN: "neutral",
} as const;

function fmtNum(v: unknown, unit?: string | null): string {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return unit === "pct" ? `${n}%` : String(n);
}

// Slice 4H.6 — read-only Outcome & Performance window onto the canonical
// nine-section assessment. Presents recorded/derived/unknown truth,
// attribution levels, temporal basis, unknowns and honesty explicitly.
// Evidence composition only: no score, no verdict, no recommendation.
export function PerformancePanel({
  assessment,
}: {
  assessment: CompanyPerformanceAssessment | null;
}) {
  if (!assessment) return null;
  const { decision, observed, measured, assessed, unknown, temporal_basis } =
    assessment;
  const outcome = observed.outcome_record;
  const honestyFlags = Object.entries(assessment.honesty).filter(
    ([, v]) => v === true,
  );

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-line bg-surface/40 p-3">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
        <Activity className="h-3.5 w-3.5" /> Performance
        <Badge tone="neutral">evidence only · no score</Badge>
      </p>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px] text-muted">
        <span className="text-faint">Decision</span>
        <span>{decision.title}</span>
        <span className="text-faint">State</span>
        <span>{decision.state}</span>
        <span className="text-faint">
          Anchor ({temporal_basis.anchor_basis})
        </span>
        <span>
          {temporal_basis.anchor ? timeAgo(temporal_basis.anchor) : "—"}
        </span>

        <span className="text-faint">Outcome (recorded)</span>
        <span className="flex items-center gap-1.5">
          {outcome.outcome_kind ?? <span>none recorded</span>}
          <Badge tone={TRUTH_TONE[outcome.truth] ?? "neutral"}>
            {outcome.truth}
          </Badge>
        </span>
        <span className="text-faint">Effectiveness (recorded value)</span>
        <span className="flex items-center gap-1.5">
          {fmtNum(outcome.effectiveness)}
          {outcome.effectiveness != null && (
            <Badge tone="success">recorded</Badge>
          )}
        </span>
        <span className="text-faint">Execution evidence</span>
        <span>
          {observed.execution_actions_count} actions ·{" "}
          {observed.evidence_events_count} events
        </span>
      </div>

      {measured.items.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
            Measured change
          </p>
          {measured.items.map((item) => {
            const m = item.measurement;
            const tb = (m?.temporal_basis ?? {}) as Record<
              string,
              string | null
            >;
            return (
              <div
                key={item.metric.key}
                className="rounded-md border border-line p-2 text-[12px]"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="brand">{item.metric.name}</Badge>
                  {m && (
                    <Badge tone={TRUTH_TONE[m.truth] ?? "neutral"}>
                      {m.truth}
                    </Badge>
                  )}
                  <Badge
                    tone={ATTRIBUTION_TONE[item.attribution.level] ?? "neutral"}
                  >
                    {item.attribution.level}
                  </Badge>
                </div>
                {m ? (
                  <>
                    <p className="mt-1 text-muted">
                      baseline{" "}
                      {fmtNum(
                        (m.baseline as Record<string, unknown>)?.value,
                        item.metric.unit,
                      )}{" "}
                      → comparison{" "}
                      {fmtNum(
                        (m.comparison as Record<string, unknown>)?.value,
                        item.metric.unit,
                      )}{" "}
                      · change{" "}
                      {m.value != null
                        ? fmtNum(m.value, item.metric.unit)
                        : "unknown"}
                      {m.percentage_delta != null &&
                        ` (${m.percentage_delta}%)`}
                    </p>
                    {tb.baseline_as_of || tb.comparison_as_of ? (
                      <p className="text-[11px] text-faint">
                        baseline as of {tb.baseline_as_of ?? "—"} · comparison
                        as of {tb.comparison_as_of ?? "—"}
                        {tb.window_days != null &&
                          ` · window ${String(tb.window_days)}d`}
                      </p>
                    ) : null}
                    {m.basis && (
                      <p className="text-[11px] text-faint">
                        derived from observations{" "}
                        {m.basis.baseline_observation_id} →{" "}
                        {m.basis.comparison_observation_id}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="mt-1 text-faint">no measurable change yet</p>
                )}
                {item.attribution.reason && (
                  <p className="text-[11px] text-faint">
                    {item.attribution.reason}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-md border border-line p-2 text-[12px]">
        <p className="font-semibold text-muted">Assessment (evidence counts)</p>
        <p className="mt-0.5 text-faint">
          outcome recorded: {String(assessed.outcome_recorded)} · linked
          metrics: {assessed.linked_metrics_count} · derived measurements:{" "}
          {assessed.derived_measurements_count} · attribution S/A/U:{" "}
          {assessed.attribution_summary.SUPPORTED ?? 0}/
          {assessed.attribution_summary.ASSOCIATED ?? 0}/
          {assessed.attribution_summary.UNKNOWN ?? 0}
        </p>
      </div>

      {unknown.count > 0 && (
        <div className="rounded-md border border-warning/30 bg-warning/10 p-2 text-[12px]">
          <p className="font-semibold text-muted">
            What remains unknown ({unknown.count})
          </p>
          <ul className="mt-0.5 space-y-0.5">
            {unknown.items.slice(0, 6).map((u, idx) => (
              <li key={idx} className="text-faint">
                {u.section}/{u.subject}: {u.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="flex flex-wrap gap-1">
        {honestyFlags.map(([flag]) => (
          <Badge key={flag} tone="neutral">
            {flag.replaceAll("_", " ")}
          </Badge>
        ))}
      </p>
    </div>
  );
}

export function CompanyTab() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role || "", PERMISSIONS.PROJECTS_MANAGE);

  const [state, setState] = useState<CompanyStateResponse | null>(null);
  const [health, setHealth] = useState<CompanyHealthResponse | null>(null);
  const [recommendations, setRecommendations] =
    useState<CompanyRecommendationsResponse | null>(null);
  const [changes, setChanges] = useState<CompanyChangesResponse | null>(null);
  const [memory, setMemory] = useState<CompanyMemoryResponse | null>(null);
  const [narrative, setNarrative] = useState<CompanyNarrativeResponse | null>(
    null,
  );
  const [trail, setTrail] = useState<CompanyTemporalSeriesResponse | null>(
    null,
  );

  const [chain, setChain] = useState<CompanyCausalChainResponse | null>(null);
  const [chainSubjectType, setChainSubjectType] = useState("project");
  const [chainSubjectId, setChainSubjectId] = useState("");
  const [chainLoading, setChainLoading] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actingKey, setActingKey] = useState<string | null>(null);

  const [scenario, setScenario] = useState<"delay" | "hire">("delay");
  const [whatIfPayload, setWhatIfPayload] = useState<Record<string, string>>({
    project_id: "",
    days: "21",
    capability: "",
    people: "2",
    ramp_days: "30",
  });
  const [whatIf, setWhatIf] = useState<CompanyWhatIfResponse | null>(null);
  const [running, setRunning] = useState(false);

  const [outcomeForm, setOutcomeForm] = useState<
    Record<string, { kind: string; effectiveness: string; lesson: string }>
  >({});

  const [evalForm, setEvalForm] = useState({
    kind: "hire",
    title: "",
    rationale: "",
    alternativeLabel: "",
  });
  const [evalBusy, setEvalBusy] = useState(false);
  const [recommending, setRecommending] = useState<string | null>(null);
  const [intel, setIntel] = useState<
    Record<string, Record<string, unknown> | null>
  >({});
  const [intelBusy, setIntelBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [s, h, r, c, m, n, t] = await Promise.all([
        getCompanyState(),
        getCompanyOperatingHealth(),
        getCompanyRecommendations(),
        getCompanyChanges(),
        getCompanyMemory(),
        getCompanyNarrative(),
        getCompanyTemporalSeries(),
      ]);
      setState(s);
      setHealth(h);
      setRecommendations(r);
      setChanges(c);
      setMemory(m);
      setNarrative(n);
      setTrail(t);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load the company operating view",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const domainStates = (health?.domains ?? []).filter((d) =>
    ["at_risk", "critical"].includes(d.state),
  );
  const domainScores = (health?.domains ?? []).map((d) => d.score);
  const avgScore = domainScores.length
    ? Math.round(domainScores.reduce((a, b) => a + b, 0) / domainScores.length)
    : 0;

  async function approve(recommendation: {
    key: string;
    source: string;
    kind: string;
    title: string;
    why?: string;
    impact_label?: string;
    owner_label: string;
    expected_improvement: string;
    confidence: string;
  }) {
    if (!canManage) return;
    setActingKey(recommendation.key);
    setActionError(null);
    try {
      await recordCompanyDecision({
        kind: decisionKindFor(recommendation),
        title: recommendation.title,
        recommendation_key: recommendation.key,
        rationale:
          recommendation.why ??
          "approved from the company recommendation queue",
        impact_label: recommendation.impact_label,
        expected_improvement: recommendation.expected_improvement,
        confidence:
          recommendation.confidence === "high"
            ? 0.8
            : recommendation.confidence === "medium"
              ? 0.6
              : 0.4,
        owner_label: recommendation.owner_label,
      });
      await refresh();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to record the decision",
      );
    } finally {
      setActingKey(null);
    }
  }

  async function execute(decision: CompanyDecisionRow) {
    setActingKey(decision.decision_id);
    setActionError(null);
    try {
      await executeCompanyDecision(decision.decision_id);
      await refresh();
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Unable to mark the decision as executed",
      );
    } finally {
      setActingKey(null);
    }
  }

  async function recordOutcome(decision: CompanyDecisionRow) {
    const form = outcomeForm[decision.decision_id];
    if (!form) return;
    setActingKey(decision.decision_id);
    setActionError(null);
    try {
      await recordCompanyOutcome(decision.decision_id, {
        outcome_kind: form.kind,
        effectiveness: form.effectiveness
          ? Math.max(0, Math.min(1, Number(form.effectiveness)))
          : undefined,
        lesson: form.lesson.trim() || undefined,
      });
      await refresh();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to record the outcome",
      );
    } finally {
      setActingKey(null);
    }
  }

  async function evaluateNew() {
    if (!evalForm.title.trim()) {
      setActionError("Title is required");
      return;
    }
    setEvalBusy(true);
    setActionError(null);
    try {
      await evaluateCompanyDecision({
        kind: evalForm.kind,
        title: evalForm.title.trim(),
        rationale: evalForm.rationale.trim() || undefined,
        alternatives: [
          {
            alternative_key: "alt:01",
            label: evalForm.alternativeLabel.trim() || evalForm.title.trim(),
            chosen: true,
            why_chosen: "chosen by the requester",
          },
          {
            alternative_key: "alt:02",
            label: "Do nothing",
            chosen: false,
            why_not: "no change required",
          },
        ],
      });
      setEvalForm({
        kind: "hire",
        title: "",
        rationale: "",
        alternativeLabel: "",
      });
      await refresh();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to evaluate the decision",
      );
    } finally {
      setEvalBusy(false);
    }
  }

  async function recommend(decision: CompanyDecisionRow) {
    setRecommending(decision.decision_id);
    setActionError(null);
    try {
      await recommendCompanyDecision(decision.decision_id);
      await refresh();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to recommend the decision",
      );
    } finally {
      setRecommending(null);
    }
  }

  async function toggleIntel(decisionId: string) {
    if (intel[decisionId]) {
      setIntel((s) => {
        const next = { ...s };
        delete next[decisionId];
        return next;
      });
      return;
    }
    setIntelBusy(decisionId);
    setActionError(null);
    try {
      const [
        prediction,
        quality,
        alternatives,
        whyNot,
        precedents,
        contradictions,
        impact,
      ] = await Promise.all([
        getCompanyDecisionPrediction(decisionId),
        getCompanyDecisionQuality(decisionId),
        getCompanyDecisionAlternatives(decisionId),
        getCompanyDecisionWhyNot(decisionId),
        getCompanyDecisionPrecedents(decisionId),
        getCompanyDecisionContradictions(decisionId),
        getCompanyDecisionImpact(decisionId),
      ]);
      setIntel((s) => ({
        ...s,
        [decisionId]: {
          prediction,
          quality,
          alternatives,
          whyNot,
          precedents,
          contradictions,
          impact,
        },
      }));
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Unable to load decision intelligence",
      );
    } finally {
      setIntelBusy(null);
    }
  }

  async function runWhatIf() {
    setRunning(true);
    setActionError(null);
    try {
      const payload: Record<string, string | number> = {};
      if (scenario === "delay") {
        payload.project_id = whatIfPayload.project_id.trim();
        payload.days = Number(whatIfPayload.days) || 0;
      } else {
        payload.capability = whatIfPayload.capability.trim();
        payload.people = Number(whatIfPayload.people) || 1;
        payload.ramp_days = Number(whatIfPayload.ramp_days) || 0;
      }
      setWhatIf(await runCompanyWhatHappensIf(scenario, payload));
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to run the what-if",
      );
    } finally {
      setRunning(false);
    }
  }

  async function runChain() {
    if (!chainSubjectId.trim()) return;
    setChainLoading(true);
    setActionError(null);
    try {
      setChain(
        await getCompanyCausalChain(
          chainSubjectType.trim(),
          chainSubjectId.trim(),
        ),
      );
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to walk the causal chain",
      );
    } finally {
      setChainLoading(false);
    }
  }

  // ---- Slice 4H.4 — decision rehearsal (read-only; recording stays a governed API act).
  const [rehearseKind, setRehearseKind] = useState("delay");
  const [rehearseSubjectType, setRehearseSubjectType] = useState("project");
  const [rehearseSubjectId, setRehearseSubjectId] = useState("");
  const [rehearsal, setRehearsal] =
    useState<CompanyScenarioRehearseResponse | null>(null);
  const [history, setHistory] = useState<CompanyScenarioHistoryResponse | null>(
    null,
  );
  const [compare, setCompare] = useState<CompanyScenarioCompareResponse | null>(
    null,
  );
  const [rehearseBusy, setRehearseBusy] = useState(false);
  const [compareBusy, setCompareBusy] = useState(false);

  useEffect(() => {
    listCompanyScenarios(10)
      .then(setHistory)
      .catch(() => {});
  }, []);

  async function runRehearsal(record: boolean) {
    if (!rehearseSubjectType.trim() || !rehearseSubjectId.trim()) return;
    setRehearseBusy(true);
    setActionError(null);
    try {
      setRehearsal(
        await rehearseCompanyScenario({
          scenario_kind: rehearseKind,
          subject_type: rehearseSubjectType.trim(),
          subject_id: rehearseSubjectId.trim(),
          scope_type: "org",
          dry_run: !record,
        }),
      );
      setHistory(await listCompanyScenarios(10));
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to rehearse the scenario",
      );
    } finally {
      setRehearseBusy(false);
    }
  }

  async function runScenarioCompare() {
    const ids = (history?.scenarios ?? [])
      .slice(0, 5)
      .map((s) => s.scenario_id);
    if (ids.length < 2) return;
    setCompareBusy(true);
    setActionError(null);
    try {
      setCompare(await compareCompanyScenarios(ids));
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to compare scenarios",
      );
    } finally {
      setCompareBusy(false);
    }
  }

  // ---- Slice 4H.5 — decision-to-action lineage: derive the advisory plan,
  // review it, authorize a step through the EXISTING governed propose route
  // with decision lineage, and read the live execution chain.
  const [lineageDecisionId, setLineageDecisionId] = useState("");
  const [plan, setPlan] = useState<CompanyActionPlanResponse | null>(null);
  const [execChain, setExecChain] =
    useState<CompanyExecutionChainResponse | null>(null);
  const [lineageBusy, setLineageBusy] = useState(false);
  const [authorizingStep, setAuthorizingStep] = useState<number | null>(null);

  async function refreshChain(decisionId: string) {
    companyExecutionChain(decisionId)
      .then(setExecChain)
      .catch(() => {});
  }

  async function runLineage() {
    const id = lineageDecisionId.trim();
    if (!id) return;
    setLineageBusy(true);
    setActionError(null);
    try {
      const [p, c] = await Promise.all([
        deriveCompanyActionPlan(id),
        companyExecutionChain(id).catch(() => null),
      ]);
      setPlan(p);
      setExecChain(c);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to derive the action plan",
      );
    } finally {
      setLineageBusy(false);
    }
  }

  async function authorizeStep(step: CompanyActionPlanStep) {
    if (!plan) return;
    setAuthorizingStep(step.step_no);
    setActionError(null);
    try {
      await brainKnowledgeActionPropose({
        action_type: step.action_type,
        title: step.title,
        source_problem: plan.decision.title,
        target: step.target.label ?? step.target.id,
        scope_type: "org",
        risk: "low",
        source_company_decision_id: plan.decision.decision_id,
      });
      await refreshChain(plan.decision.decision_id);
      setPlan(await deriveCompanyActionPlan(plan.decision.decision_id));
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Unable to authorize the step",
      );
    } finally {
      setAuthorizingStep(null);
    }
  }

  // ---- Slice 4H.6 — read-only performance intelligence. Attached to the
  // decision (never a separate analytics product); cohort and comparison are
  // neutral evidence views with no winner, rank, or score anywhere.
  const [perf, setPerf] = useState<
    Record<string, CompanyPerformanceAssessment | null>
  >({});
  const [perfBusy, setPerfBusy] = useState<string | null>(null);
  const [cohort, setCohort] = useState<CompanyPerformanceCohortResponse | null>(
    null,
  );
  const [cohortBusy, setCohortBusy] = useState(false);
  const [compareIds, setCompareIds] = useState("");
  const [comparison, setComparison] =
    useState<CompanyPerformanceComparisonResponse | null>(null);
  const [comparePerfBusy, setComparePerfBusy] = useState(false);

  async function togglePerformance(decisionId: string) {
    if (perf[decisionId]) {
      setPerf((s) => {
        const next = { ...s };
        delete next[decisionId];
        return next;
      });
      return;
    }
    setPerfBusy(decisionId);
    setActionError(null);
    try {
      const assessment = await getCompanyDecisionPerformance(decisionId);
      setPerf((s) => ({ ...s, [decisionId]: assessment }));
    } catch {
      setPerf((s) => ({ ...s, [decisionId]: null }));
      setActionError("Unable to load the performance assessment");
    } finally {
      setPerfBusy(null);
    }
  }

  async function loadCohort() {
    setCohortBusy(true);
    setActionError(null);
    try {
      setCohort(await getCompanyPerformanceCohort());
    } catch {
      setActionError("Unable to load the outcome history");
    } finally {
      setCohortBusy(false);
    }
  }

  async function runDecisionCompare() {
    const ids = compareIds
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 5);
    if (ids.length < 2) return;
    setComparePerfBusy(true);
    setActionError(null);
    try {
      setComparison(await compareCompanyDecisions(ids));
    } catch (err) {
      const detail = (err as { detail?: { reason?: string } }).detail;
      setActionError(
        detail?.reason
          ? `Comparison rejected: ${detail.reason}`
          : "Unable to compare the decisions",
      );
    } finally {
      setComparePerfBusy(false);
    }
  }

  const dimensions = state?.dimensions ?? {};
  const dimKeys = Object.keys(dimensions);

  if (error && !health && !loading) {
    return (
      <ErrorState
        title="Could not load company operating intelligence"
        message={error}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="Company score"
          value={loading ? "…" : (health?.company_score ?? "—")}
          icon={HeartPulse}
        />
        <StatCard
          label="Company state"
          value={loading ? "…" : (health?.company_state ?? "—")}
          icon={Target}
        />
        <StatCard
          label="Domains at risk"
          value={loading ? "…" : domainStates.length}
          icon={AlertTriangle}
        />
        <StatCard
          label="Attention items"
          value={loading ? "…" : (state?.attention ?? []).length}
          icon={ListChecks}
        />
        <StatCard
          label="Recommendations"
          value={loading ? "…" : (recommendations?.total ?? 0)}
          icon={Activity}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title="Universal company state"
            subtitle="One composed picture of the company as a whole — every dimension is the canonical engine's own output, bounded."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Composing the
                company state
              </div>
            ) : dimKeys.length === 0 ? (
              <EmptyState
                icon={Target}
                title="No company state yet"
                description="The eight dimensions appear once the company has real activity across the canonical systems."
              />
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2">
                {dimKeys.map((key) => {
                  const dim = dimensions[key];
                  return (
                    <li
                      key={key}
                      className="rounded-lg border border-line/70 bg-elevated p-3"
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone="brand">{dim.label ?? key}</Badge>
                        {dim.state && (
                          <Badge tone={STATE_TONE[dim.state] ?? "neutral"}>
                            {dim.state}
                          </Badge>
                        )}
                      </div>
                      {dim.headline && (
                        <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
                          {dim.headline}
                        </p>
                      )}
                      {key === "capacity" && dim.top_constraint?.capability && (
                        <p className="mt-1.5 text-[11px] text-faint">
                          top constraint:{" "}
                          <span className="text-ink">
                            {dim.top_constraint.capability}
                          </span>
                          {dim.top_constraint.gap != null
                            ? ` · gap ${dim.top_constraint.gap}`
                            : ""}
                        </p>
                      )}
                      {(dim.goals ?? []).length > 0 && (
                        <p className="mt-1.5 flex flex-wrap gap-1">
                          {(dim.goals ?? []).map((g) => (
                            <Badge key={g.goal_id ?? g.title} tone="neutral">
                              {g.title}
                            </Badge>
                          ))}
                        </p>
                      )}
                      {(dim.projects ?? []).length > 0 && (
                        <p className="mt-1.5 text-[11px] text-faint">
                          {(dim.projects ?? []).map((p) => p.name).join(" · ")}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card
            title={`Company health · ${health?.company_score ?? "—"}/100 (${avgScore} domain average)`}
            subtitle={
              health?.summary ??
              "Eight explainable domains — every score carries the reasons and the primary constraint carries its root cause."
            }
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Assessing the
                eight domains
              </div>
            ) : (health?.domains ?? []).length === 0 ? (
              <EmptyState
                icon={HeartPulse}
                title="No health assessment yet"
                description="Company activity produces the exact-once health trail — replays converge, history answers what changed."
              />
            ) : (
              <>
                <ul className="space-y-3">
                  {(health?.domains ?? []).map((row) => (
                    <li
                      key={row.key}
                      className="rounded-lg border border-line/70 bg-elevated p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="brand">{row.label}</Badge>
                        <Badge tone={STATE_TONE[row.state] ?? "neutral"}>
                          {row.state}
                        </Badge>
                        <span className="text-[12px] font-semibold text-ink">
                          {row.score}/100
                        </span>
                        {row.evidence_count > 0 && (
                          <span className="ml-auto text-[11px] text-faint">
                            {row.evidence_count} evidence
                          </span>
                        )}
                      </div>
                      {row.reasons.length > 0 && (
                        <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          {row.reasons.map((reason) => (
                            <Badge key={reason} tone="warning">
                              {reason}
                            </Badge>
                          ))}
                        </p>
                      )}
                      {row.positives.length > 0 && (
                        <p className="mt-1 flex flex-wrap items-center gap-1.5">
                          {row.positives.map((positive) => (
                            <Badge key={positive} tone="success">
                              {positive}
                            </Badge>
                          ))}
                        </p>
                      )}
                      {row.constraint && (
                        <div className="mt-2 rounded-lg border border-danger/20 bg-danger/5 px-3 py-2">
                          <p className="text-[12px] font-medium text-ink">
                            <AlertTriangle className="mr-1 inline h-3.5 w-3.5 text-danger" />
                            {row.constraint.label}
                          </p>
                          {row.constraint.detail && (
                            <p className="mt-0.5 text-[11px] text-muted">
                              {row.constraint.detail}
                            </p>
                          )}
                          {row.root_cause && (
                            <p className="mt-0.5 text-[11px] text-faint">
                              root cause: {row.root_cause}
                            </p>
                          )}
                          {row.interventions.length > 0 && (
                            <p className="mt-1 flex flex-wrap gap-1">
                              {row.interventions.map((intervention) => (
                                <Badge key={intervention} tone="brand">
                                  {intervention}
                                </Badge>
                              ))}
                            </p>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                {health?.primary_constraint && (
                  <div className="mt-3 rounded-lg border border-brand/30 bg-brand/5 px-3 py-2">
                    <p className="text-[12px] font-semibold text-ink">
                      Primary company constraint ·{" "}
                      {health.primary_constraint.domain_label ??
                        health.primary_constraint.domain}
                      {health.primary_constraint.score != null &&
                        ` (${health.primary_constraint.score}/100)`}
                    </p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                      {health.primary_constraint.label}
                      {health.primary_constraint.detail
                        ? ` — ${health.primary_constraint.detail}`
                        : ""}
                    </p>
                  </div>
                )}
                {(health?.history ?? []).length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-[12px] font-semibold text-ink">
                      Health trail · {health?.history.length} assessments
                    </summary>
                    <ol className="mt-2 space-y-1">
                      {(health?.history ?? []).map((h, idx) => (
                        <li
                          key={idx}
                          className="flex flex-wrap items-center gap-2 text-[11px] text-faint"
                        >
                          <Badge
                            tone={STATE_TONE[h.company_state] ?? "neutral"}
                          >
                            {h.company_state}
                          </Badge>
                          <span className="font-medium text-ink">
                            {h.company_score}/100
                          </span>
                          {h.event_name && <span>{h.event_name}</span>}
                          <span className="ml-auto">
                            {timeAgo(h.occurred_at)}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </>
            )}
          </Card>

          <Card
            title={`What changed · ${changes?.window ?? "no window yet"}`}
            subtitle="Real deltas over the exact-once health trail — improved, declined, or the constraint moving."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Diffing the
                trail
              </div>
            ) : (changes?.changes ?? []).length === 0 ? (
              <EmptyState
                icon={History}
                title="Nothing changed"
                description="No meaningful company-level delta between the last two assessments."
              />
            ) : (
              <>
                {changes?.company_score_before != null &&
                  changes?.company_score_after != null && (
                    <p className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
                      <Badge tone="neutral">
                        {changes.company_state_before ?? "—"}
                      </Badge>
                      <span className="font-semibold text-ink">
                        {changes.company_score_before}
                      </span>
                      <ArrowRight className="h-3.5 w-3.5 text-faint" />
                      <Badge
                        tone={
                          STATE_TONE[changes.company_state_after ?? ""] ??
                          "neutral"
                        }
                      >
                        {changes.company_state_after ?? "—"}
                      </Badge>
                      <span className="font-semibold text-ink">
                        {changes.company_score_after}
                      </span>
                    </p>
                  )}
                <ul className="space-y-2">
                  {(changes?.changes ?? []).map((row, idx) => (
                    <li
                      key={idx}
                      className="rounded-lg border border-line/70 bg-elevated p-3"
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={CHANGE_TONE[row.kind] ?? "neutral"}>
                          {row.kind}
                        </Badge>
                        {row.domain && (
                          <Badge tone="neutral">{row.domain}</Badge>
                        )}
                        <p className="text-[12px] font-medium text-ink">
                          {row.label}
                        </p>
                      </div>
                      {row.why_matters && (
                        <p className="mt-1 text-[11px] leading-relaxed text-muted">
                          {row.why_matters}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title={`Company story · ${narrative?.window ?? "no window yet"}`}
            subtitle="Why the score moved — deltas composed from the trail with their evidence, deterministic and bounded."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Composing the
                story
              </div>
            ) : narrative?.window === "insufficient_history" ? (
              <EmptyState
                icon={History}
                title="Story opens with two trail points"
                description="Not enough assessments recorded yet — the narrative appears once the company trail holds at least two points."
              />
            ) : (
              <>
                <ul className="space-y-1.5">
                  {(narrative?.story ?? []).map((sentence, idx) => (
                    <li
                      key={idx}
                      className="rounded-lg border border-line/70 bg-elevated px-3 py-2 text-[12px] text-ink"
                    >
                      {sentence}
                    </li>
                  ))}
                </ul>
                {(narrative?.steps ?? []).length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-[12px] font-semibold text-ink">
                      Steps · {narrative?.steps.length}
                    </summary>
                    <ol className="mt-2 space-y-2">
                      {(narrative?.steps ?? []).map((step, idx) => (
                        <li
                          key={idx}
                          className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                        >
                          <p className="flex flex-wrap items-center gap-1.5 text-[11px]">
                            <Badge
                              tone={STATE_TONE[step.state_before] ?? "neutral"}
                            >
                              {step.state_before}
                            </Badge>
                            <span className="font-semibold text-ink">
                              {step.score_before}
                            </span>
                            <ArrowRight className="h-3 w-3 text-faint" />
                            <Badge
                              tone={STATE_TONE[step.state_after] ?? "neutral"}
                            >
                              {step.state_after}
                            </Badge>
                            <span className="font-semibold text-ink">
                              {step.score_after}
                            </span>
                          </p>
                          {(step.deltas ?? []).length > 0 && (
                            <ul className="mt-1.5 flex flex-wrap gap-1.5">
                              {step.deltas.map((delta, dIdx) => (
                                <Badge
                                  key={dIdx}
                                  tone={
                                    delta.direction === "down"
                                      ? "danger"
                                      : "success"
                                  }
                                >
                                  {delta.label ?? delta.domain}{" "}
                                  {delta.delta > 0 ? "+" : ""}
                                  {delta.delta}
                                </Badge>
                              ))}
                            </ul>
                          )}
                          {step.constraint_shift && (
                            <p className="mt-1 text-[11px] text-faint">
                              constraint shifted: {step.constraint_shift}
                            </p>
                          )}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
                {(trail?.series ?? []).length > 1 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[12px] font-semibold text-ink">
                      Trail · {trail?.count ?? 0} exact-once assessments
                    </summary>
                    <ol className="mt-2 space-y-1">
                      {(trail?.series ?? []).map((step, idx) => (
                        <li
                          key={idx}
                          className="flex flex-wrap items-center gap-2 text-[11px] text-faint"
                        >
                          <Badge
                            tone={STATE_TONE[step.company_state] ?? "neutral"}
                          >
                            {step.company_state}
                          </Badge>
                          <span className="font-medium text-ink">
                            {step.company_score}/100
                          </span>
                          {step.primary_constraint && (
                            <span>{step.primary_constraint}</span>
                          )}
                          <span className="ml-auto">
                            {timeAgo(step.occurred_at)}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </>
            )}
          </Card>

          <Card
            title={`Causal chain · ${chain?.subject.type ?? "bounded walk"}`}
            subtitle="Walk the derived causality graph from a subject — confidence and evidence per hop, never faked hops."
          >
            <div className="space-y-2">
              <div className="flex gap-1.5">
                {(
                  [
                    "project",
                    "person",
                    "customer",
                    "milestone",
                    "capability",
                    "task",
                  ] as const
                ).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setChainSubjectType(t)}
                    className={`flex-1 rounded-lg border px-2 py-1.5 text-[11px] font-medium transition-colors ${
                      chainSubjectType === t
                        ? "border-brand/40 bg-brand/10 text-brand"
                        : "border-line bg-surface text-faint hover:text-ink"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <div className="flex gap-1.5">
                <input
                  value={chainSubjectId}
                  onChange={(e) => setChainSubjectId(e.target.value)}
                  placeholder={`${chainSubjectType} id`}
                  className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={runChain}
                  disabled={chainLoading}
                >
                  {chainLoading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ArrowRight className="h-3.5 w-3.5" />
                  )}
                  Walk
                </Button>
              </div>
              {chain && (
                <div className="space-y-1.5">
                  <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-faint">
                    <Badge tone="neutral">
                      {chain.subject.type}: {chain.subject.id.slice(0, 8)}…
                    </Badge>
                    <span>depth {chain.depth}</span>
                    {chain.bounded && <Badge tone="warning">bounded</Badge>}
                  </p>
                  {(chain.hops ?? []).length === 0 ? (
                    <p className="rounded-lg border border-line/70 bg-surface px-3 py-2 text-[11px] text-faint">
                      No hops in the snapshot for this subject — the graph stays
                      evidence-driven.
                    </p>
                  ) : (
                    <ul className="space-y-1">
                      {chain.hops.map((hop, idx) => (
                        <li
                          key={idx}
                          className="rounded-lg border border-line/70 bg-surface px-3 py-2 text-[11px]"
                        >
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-medium text-ink">
                              {hop.from_label ?? hop.from_id.slice(0, 8)}
                            </span>
                            <Badge
                              tone={
                                HOP_KIND_TONE[
                                  hop.kind.replace(" (reverse)", "")
                                ] ?? "neutral"
                              }
                            >
                              {hop.kind}
                            </Badge>
                            <span className="font-medium text-ink">
                              {hop.to_label ?? hop.to_id.slice(0, 8)}
                            </span>
                            <Badge tone="neutral">{hop.confidence}</Badge>
                            {hop.reverse && (
                              <Badge tone="neutral">reverse</Badge>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card
            title={`Attention · ${(state?.attention ?? []).length}`}
            subtitle="What the company as a whole should pay attention to next."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ranking
                attention
              </div>
            ) : (state?.attention ?? []).length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="Nothing urgent"
                description="Attention builds from the composed company state across the eight dimensions."
              />
            ) : (
              <ol className="space-y-1.5">
                {(state?.attention ?? []).map((item, idx) => (
                  <li
                    key={idx}
                    className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge
                        tone={
                          item.priority === 1
                            ? "danger"
                            : item.priority === 2
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {item.priority}
                      </Badge>
                      <Badge tone="brand">{item.kind}</Badge>
                    </div>
                    <p className="mt-1 text-[12px] font-medium text-ink">
                      {item.title}
                    </p>
                    {item.why && (
                      <p className="mt-0.5 text-[11px] text-faint">
                        {item.why}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card
            title={`Recommendations · ${recommendations?.total ?? 0}`}
            subtitle="The universal queue — every item carries its impact, confidence, owner and evidence; nothing executes without human approval."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Deriving the
                queue
              </div>
            ) : (recommendations?.recommendations ?? []).length === 0 ? (
              <EmptyState
                icon={CircleDashed}
                title="Nothing to recommend"
                description="Recommendations derive deterministically from the composed company state."
              />
            ) : (
              <ul className="space-y-2">
                {(recommendations?.recommendations ?? []).map((row) => (
                  <li
                    key={row.key}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={SOURCE_TONE[row.source] ?? "neutral"}>
                        {row.source}
                      </Badge>
                      <Badge tone="neutral">{row.kind}</Badge>
                      <span className="ml-auto text-[11px] text-faint">
                        {row.confidence}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] font-medium text-ink">
                      {row.title}
                    </p>
                    {row.why && (
                      <p className="mt-0.5 text-[11px] text-faint">{row.why}</p>
                    )}
                    <p className="mt-0.5 text-[11px] text-muted">
                      {row.expected_improvement}
                      {row.owner_label ? ` · ${row.owner_label}` : ""}
                    </p>
                    {row.impact_label && (
                      <p className="mt-0.5 text-[11px] text-faint">
                        {row.impact_label}
                      </p>
                    )}
                    {canManage ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        className="mt-2"
                        onClick={() => approve(row)}
                        disabled={actingKey === row.key}
                      >
                        {actingKey === row.key ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        )}
                        Approve as decision
                      </Button>
                    ) : (
                      <p className="mt-2 text-[11px] text-faint">
                        Approving recommendations requires project management
                        access.
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="What-if"
            subtitle="Bounded deterministic consequences — declared, never a prediction, never executed."
          >
            <div className="space-y-2">
              <div className="flex gap-1.5">
                {(["delay", "hire"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setScenario(s)}
                    className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors ${
                      scenario === s
                        ? "border-brand/40 bg-brand/10 text-brand"
                        : "border-line bg-surface text-faint hover:text-ink"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
              {scenario === "delay" ? (
                <input
                  value={whatIfPayload.project_id}
                  onChange={(e) =>
                    setWhatIfPayload({
                      ...whatIfPayload,
                      project_id: e.target.value,
                    })
                  }
                  placeholder="project id"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                />
              ) : (
                <input
                  value={whatIfPayload.capability}
                  onChange={(e) =>
                    setWhatIfPayload({
                      ...whatIfPayload,
                      capability: e.target.value,
                    })
                  }
                  placeholder="capability (e.g. platform_eng)"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                />
              )}
              <div className="grid grid-cols-3 gap-1.5">
                {scenario === "delay" ? (
                  <>
                    <input
                      value={whatIfPayload.days}
                      onChange={(e) =>
                        setWhatIfPayload({
                          ...whatIfPayload,
                          days: e.target.value,
                        })
                      }
                      placeholder="days"
                      className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                    />
                    <span className="text-[11px] text-faint" />
                    <span className="text-[11px] text-faint" />
                  </>
                ) : (
                  <>
                    <input
                      value={whatIfPayload.people}
                      onChange={(e) =>
                        setWhatIfPayload({
                          ...whatIfPayload,
                          people: e.target.value,
                        })
                      }
                      placeholder="people"
                      className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                    />
                    <input
                      value={whatIfPayload.ramp_days}
                      onChange={(e) =>
                        setWhatIfPayload({
                          ...whatIfPayload,
                          ramp_days: e.target.value,
                        })
                      }
                      placeholder="ramp days"
                      className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                    />
                    <span className="text-[11px] text-faint" />
                  </>
                )}
              </div>
              <Button
                size="sm"
                className="w-full"
                onClick={runWhatIf}
                disabled={running}
              >
                {running ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FlaskConical className="h-4 w-4" />
                )}
                Run what-if
              </Button>
              {whatIf && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="brand">{whatIf.scenario_type}</Badge>
                    {whatIf.not_a_prediction && (
                      <Badge tone="neutral">not a prediction</Badge>
                    )}
                  </div>
                  <ul className="space-y-1.5">
                    {whatIf.consequences.map((c, idx) => (
                      <li
                        key={idx}
                        className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                      >
                        <div className="flex flex-wrap items-center gap-1.5">
                          <p className="text-[12px] font-medium text-ink">
                            {c.label}
                          </p>
                          <Badge tone="neutral">{c.confidence}</Badge>
                        </div>
                        {c.detail && (
                          <p className="mt-0.5 text-[11px] text-faint">
                            {c.detail}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                  {(whatIf.company_consequences ?? []).length > 0 && (
                    <>
                      <p className="flex flex-wrap items-center gap-1.5">
                        <Badge tone="brand">company hops</Badge>
                        {(whatIf.company_hop_kinds ?? []).map((kind) => (
                          <Badge key={kind} tone="neutral">
                            {kind}
                          </Badge>
                        ))}
                      </p>
                      <ul className="space-y-1.5">
                        {(whatIf.company_consequences ?? []).map((c, idx) => (
                          <li
                            key={idx}
                            className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center gap-1.5">
                              <p className="text-[12px] font-medium text-ink">
                                {c.label}
                              </p>
                              <Badge tone="neutral">{c.confidence}</Badge>
                            </div>
                            {c.detail && (
                              <p className="mt-0.5 text-[11px] text-faint">
                                {c.detail}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {whatIf.note && (
                    <p className="text-[11px] leading-relaxed text-muted">
                      {whatIf.note}
                    </p>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Scenario rehearsal"
            subtitle="4H.4: bounded, read-only decision rehearsal over declared causal edges — advisory only, never a prediction, executed only through a governed record."
          >
            <div className="space-y-2">
              <select
                value={rehearseKind}
                onChange={(e) => setRehearseKind(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-brand"
              >
                {[
                  "reallocate",
                  "delay",
                  "hire",
                  "resource_loss",
                  "dependency_break",
                  "decision_reconsider",
                ].map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-[1fr_2fr] gap-1.5">
                <select
                  value={rehearseSubjectType}
                  onChange={(e) => setRehearseSubjectType(e.target.value)}
                  className="w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-brand"
                >
                  {[
                    "project",
                    "person",
                    "capability",
                    "customer",
                    "resource",
                    "decision",
                  ].map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  value={rehearseSubjectId}
                  onChange={(e) => setRehearseSubjectId(e.target.value)}
                  placeholder="subject id (e.g. proj_... or a person key)"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                />
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => runRehearsal(false)}
                  disabled={rehearseBusy}
                >
                  {rehearseBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <FlaskConical className="h-4 w-4" />
                  )}
                  Check (dry run)
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  className="w-full"
                  onClick={() => runRehearsal(true)}
                  disabled={rehearseBusy}
                >
                  Record scenario
                </Button>
              </div>
              {rehearsal && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="brand">
                      {(
                        rehearsal.hypothetical_change as {
                          scenario_kind?: string;
                        }
                      ).scenario_kind ?? ""}
                    </Badge>
                    {rehearsal.dry_run && <Badge tone="neutral">dry run</Badge>}
                    {rehearsal.created && (
                      <Badge tone="success">recorded</Badge>
                    )}
                    {rehearsal.replayed && (
                      <Badge tone="warning">replayed exact scenario</Badge>
                    )}
                    <Badge tone="neutral">advisory only</Badge>
                  </div>
                  {rehearsal.direct_effects?.map((d, idx) => (
                    <div
                      key={idx}
                      className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                    >
                      <p className="text-[12px] font-medium text-ink">
                        {String(d.label ?? "")}
                        {d.impact && (
                          <span className="ml-1.5 text-faint">
                            · {d.impact}
                          </span>
                        )}
                      </p>
                      {d.detail && (
                        <p className="mt-0.5 text-[11px] text-faint">
                          {d.detail}
                        </p>
                      )}
                    </div>
                  ))}
                  {rehearsal.decisions_to_reconsider?.length > 0 && (
                    <p className="flex flex-wrap items-center gap-1.5">
                      <Badge tone="danger">reconsider</Badge>
                      {rehearsal.decisions_to_reconsider.map((d, idx) => (
                        <span key={idx} className="text-[12px] text-ink">
                          {String(
                            (d as { decision_id?: unknown }).decision_id ?? "",
                          )}
                        </span>
                      ))}
                    </p>
                  )}
                  <p className="text-[11px] leading-relaxed text-muted">
                    As-of {String(rehearsal.baseline?.occurred_at ?? "")} ·
                    snapshot {String(rehearsal.snapshot_ref ?? "")}
                  </p>
                </div>
              )}
              <div className="flex items-center justify-between pt-1">
                <p className="text-[11px] text-faint">
                  {history?.scenarios?.length ?? 0} recorded scenarios
                </p>
                {(history?.scenarios?.length ?? 0) >= 2 && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={runScenarioCompare}
                    disabled={compareBusy}
                  >
                    {compareBusy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <GitCompareArrows className="h-4 w-4" />
                    )}
                    Compare latest
                  </Button>
                )}
              </div>
              {compare && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="brand">comparison</Badge>
                    <Badge tone="neutral">never ranked</Badge>
                  </div>
                  {compare.scenarios?.map((s) => (
                    <div
                      key={s.scenario_id}
                      className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                    >
                      <p className="text-[12px] font-medium text-ink">
                        {s.scenario_kind} · {String(s.subject.id ?? "")}
                      </p>
                      <p className="text-[11px] text-faint">
                        {s.direct_effects.length + s.dependent_effects.length}{" "}
                        effects · {s.decisions_to_reconsider.length} to
                        reconsider
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Decision to action"
            subtitle="4H.5: derive an advisory action plan from a decision's canonical anchors, authorize a step through the existing governed route, and read the live execution chain — provenance on every node."
          >
            <div className="space-y-2">
              <div className="grid grid-cols-[2fr_1fr] gap-1.5">
                <input
                  value={lineageDecisionId}
                  onChange={(e) => setLineageDecisionId(e.target.value)}
                  placeholder="decision id (e.g. dec:hire:...)"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                />
                <Button
                  size="sm"
                  className="w-full"
                  onClick={runLineage}
                  disabled={lineageBusy}
                >
                  {lineageBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Link2 className="h-4 w-4" />
                  )}
                  Derive plan
                </Button>
              </div>
              {plan && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="brand">{plan.decision.kind}</Badge>
                    <Badge tone={STATE_TONE[plan.decision.state] ?? "neutral"}>
                      {plan.decision.state}
                    </Badge>
                    <Badge tone="neutral">advisory only</Badge>
                    {plan.honesty.derivation_status ===
                      "insufficient_canonical_basis" && (
                      <Badge tone="warning">insufficient canonical basis</Badge>
                    )}
                  </div>
                  {plan.proposed_steps.map((step) => (
                    <div
                      key={step.step_no}
                      className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-[12px] font-medium text-ink">
                            {step.step_no}. {step.title}
                          </p>
                          <p className="mt-0.5 text-[11px] text-faint">
                            {step.action_type} → {step.target.entity}:
                            {step.target.id} · basis: {step.basis.relation}
                            {step.basis.risk_id
                              ? ` · risk ${step.basis.risk_id}`
                              : ""}
                            {step.approval_expected.approval_required
                              ? " · approval expected"
                              : ""}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => authorizeStep(step)}
                          disabled={authorizingStep !== null}
                        >
                          {authorizingStep === step.step_no ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Send className="h-4 w-4" />
                          )}
                          Authorize
                        </Button>
                      </div>
                    </div>
                  ))}
                  {plan.authorized_actions.length > 0 && (
                    <p className="text-[11px] text-faint">
                      {plan.authorized_actions.length} action(s) already
                      authorized from this decision
                    </p>
                  )}
                </div>
              )}
              {execChain && (
                <div className="space-y-1.5 rounded-lg border border-line/70 bg-elevated px-3 py-2">
                  <p className="text-[12px] font-medium text-ink">
                    Execution chain
                  </p>
                  <p className="text-[11px] text-faint">
                    {execChain.actions.length} action(s) ·{" "}
                    {execChain.evidence.length} evidence ·{" "}
                    {execChain.artifacts.length} artifact(s) ·{" "}
                    {execChain.outcomes.length} outcome(s)
                    {execChain.lesson ? " · lesson recorded" : ""}
                  </p>
                  {execChain.actions.slice(0, 5).map((a) => (
                    <p key={a.action_id} className="text-[11px] text-muted">
                      <span className="text-ink">{a.title}</span> · {a.state}
                      {a.due_at ? ` · due ${timeAgo(a.due_at)}` : ""}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Evaluate a decision"
            subtitle="Advisory 4H.2: evidence + alternatives are recorded, never approved — the governed approval path stays human."
          >
            <div className="space-y-2">
              <div className="flex gap-1.5">
                <select
                  value={evalForm.kind}
                  onChange={(e) =>
                    setEvalForm({ ...evalForm, kind: e.target.value })
                  }
                  className="flex-1 rounded-lg border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-brand"
                >
                  {[
                    "hire",
                    "delay_project",
                    "reallocate_capacity",
                    "change_priority",
                    "resolve_conflict",
                    "improve_coordination",
                    "customer_mitigation",
                    "commercial_action",
                    "other",
                  ].map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
              <input
                value={evalForm.title}
                onChange={(e) =>
                  setEvalForm({ ...evalForm, title: e.target.value })
                }
                placeholder="decision title"
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
              />
              <input
                value={evalForm.alternativeLabel}
                onChange={(e) =>
                  setEvalForm({ ...evalForm, alternativeLabel: e.target.value })
                }
                placeholder="chosen option label (defaults to the title)"
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
              />
              <textarea
                value={evalForm.rationale}
                onChange={(e) =>
                  setEvalForm({ ...evalForm, rationale: e.target.value })
                }
                placeholder="rationale — what led to the decision"
                rows={2}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-brand"
              />
              <Button
                size="sm"
                className="w-full"
                onClick={evaluateNew}
                disabled={evalBusy}
              >
                {evalBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Evaluate (advisory)
              </Button>
            </div>
          </Card>

          <Card
            title={`Company memory · ${memory?.total_decisions ?? 0}`}
            subtitle="The governed loop: human approves → human executes → outcome recorded → the lesson enters company memory."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading company
                memory
              </div>
            ) : (memory?.decisions ?? []).length === 0 ? (
              <EmptyState
                icon={Lightbulb}
                title="No decisions yet"
                description="Approve a recommendation to open the governed decision loop."
              />
            ) : (
              <ul className="space-y-2">
                {(memory?.decisions ?? []).map((decision) => {
                  const form = outcomeForm[decision.decision_id] ?? {
                    kind: "successful",
                    effectiveness: "",
                    lesson: "",
                  };
                  return (
                    <li
                      key={decision.decision_id}
                      className="rounded-lg border border-line/70 bg-elevated p-3"
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={STATE_TONE[decision.state] ?? "neutral"}>
                          {decision.state}
                        </Badge>
                        <Badge tone="neutral">{decision.kind}</Badge>
                        <span className="ml-auto text-[11px] text-faint">
                          {decision.updated_at
                            ? timeAgo(decision.updated_at)
                            : ""}
                        </span>
                      </div>
                      <p className="mt-1 text-[12px] font-medium text-ink">
                        {decision.title}
                      </p>
                      {decision.predicted_outcome && (
                        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-faint">
                          <Badge tone="neutral">predicted</Badge>
                          <span>
                            {JSON.stringify(decision.predicted_outcome ?? {})}
                          </span>
                          {decision.prediction_confidence != null && (
                            <span>
                              · confidence{" "}
                              {decision.prediction_confidence.toFixed(2)}
                            </span>
                          )}
                        </p>
                      )}
                      {decision.actual_outcome_compare && (
                        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                          <Badge
                            tone={
                              decision.actual_outcome_compare.aligned
                                ? "success"
                                : "danger"
                            }
                          >
                            {decision.actual_outcome_compare.aligned
                              ? "prediction held"
                              : "prediction missed"}
                          </Badge>
                          <span className="text-faint">
                            observed{" "}
                            {decision.actual_outcome_compare.observed ?? "—"} vs
                            predicted{" "}
                            {String(
                              decision.actual_outcome_compare.predicted ?? "—",
                            )}
                          </span>
                        </p>
                      )}
                      {decision.owner_label && (
                        <p className="mt-0.5 text-[11px] text-faint">
                          owner: {decision.owner_label}
                        </p>
                      )}
                      {decision.lesson && (
                        <p className="mt-1 rounded-lg border border-brand/20 bg-brand/5 px-2 py-1.5 text-[11px] leading-relaxed text-muted">
                          <Lightbulb className="mr-1 inline h-3 w-3 text-brand" />
                          {decision.lesson}
                        </p>
                      )}
                      {decision.state === "approved" && canManage && (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="mt-2"
                          onClick={() => execute(decision)}
                          disabled={actingKey === decision.decision_id}
                        >
                          {actingKey === decision.decision_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          )}
                          Mark as executed
                        </Button>
                      )}
                      {decision.state === "executed" && canManage && (
                        <div className="mt-2 space-y-1.5">
                          <div className="flex gap-1.5">
                            <select
                              value={form.kind}
                              onChange={(e) =>
                                setOutcomeForm({
                                  ...outcomeForm,
                                  [decision.decision_id]: {
                                    ...form,
                                    kind: e.target.value,
                                  },
                                })
                              }
                              className="flex-1 rounded-lg border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-brand"
                            >
                              <option value="successful">successful</option>
                              <option value="partial">partial</option>
                              <option value="unsuccessful">unsuccessful</option>
                            </select>
                            <input
                              value={form.effectiveness}
                              onChange={(e) =>
                                setOutcomeForm({
                                  ...outcomeForm,
                                  [decision.decision_id]: {
                                    ...form,
                                    effectiveness: e.target.value,
                                  },
                                })
                              }
                              placeholder="effectiveness 0-1"
                              className="w-24 rounded-lg border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-brand"
                            />
                          </div>
                          <textarea
                            value={form.lesson}
                            onChange={(e) =>
                              setOutcomeForm({
                                ...outcomeForm,
                                [decision.decision_id]: {
                                  ...form,
                                  lesson: e.target.value,
                                },
                              })
                            }
                            placeholder="lesson for company memory"
                            rows={2}
                            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-brand"
                          />
                          <Button
                            size="sm"
                            className="w-full"
                            onClick={() => recordOutcome(decision)}
                            disabled={actingKey === decision.decision_id}
                          >
                            {actingKey === decision.decision_id ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Send className="h-3.5 w-3.5" />
                            )}
                            Record outcome + lesson
                          </Button>
                        </div>
                      )}
                      {decision.state === "evaluated" && canManage && (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="mt-2"
                          onClick={() => recommend(decision)}
                          disabled={recommending === decision.decision_id}
                        >
                          {recommending === decision.decision_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <GitCompareArrows className="h-3.5 w-3.5" />
                          )}
                          Recommend (advisory)
                        </Button>
                      )}
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() => toggleIntel(decision.decision_id)}
                          className="flex items-center gap-1.5 text-[11px] font-medium text-faint transition-colors hover:text-brand"
                        >
                          <Scale className="h-3.5 w-3.5" />
                          {intel[decision.decision_id]
                            ? "Hide decision intelligence"
                            : "Decision intelligence"}
                        </button>
                      </div>
                      <DecisionIntelPanel
                        data={intel[decision.decision_id] ?? null}
                        busy={intelBusy === decision.decision_id}
                      />
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() =>
                            togglePerformance(decision.decision_id)
                          }
                          className="flex items-center gap-1.5 text-[11px] font-medium text-faint transition-colors hover:text-brand"
                        >
                          {perfBusy === decision.decision_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <HeartPulse className="h-3.5 w-3.5" />
                          )}
                          {perf[decision.decision_id]
                            ? "Hide performance"
                            : "Outcome & performance"}
                        </button>
                      </div>
                      <PerformancePanel
                        assessment={perf[decision.decision_id] ?? null}
                      />
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card
            title="Outcome history"
            subtitle="4H.6: longitudinal outcome record over comparable decisions - institutional evidence, not a leaderboard."
          >
            {!cohort ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={loadCohort}
                disabled={cohortBusy}
              >
                {cohortBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <History className="h-3.5 w-3.5" />
                )}
                Load outcome history
              </Button>
            ) : (
              <div className="space-y-2 text-[12px] text-muted">
                <p className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="brand">
                    {cohort.cohort.decision_count} decisions
                  </Badge>
                  <Badge tone="neutral">derived on read</Badge>
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(cohort.recorded_outcomes.by_kind).map(
                    ([kind, n]) =>
                      n > 0 ? (
                        <Badge
                          key={kind}
                          tone={
                            kind === "successful"
                              ? "success"
                              : kind === "unsuccessful"
                                ? "danger"
                                : "warning"
                          }
                        >
                          {kind}: {n}
                        </Badge>
                      ) : null,
                  )}
                  {cohort.recorded_outcomes.without_outcome_record > 0 && (
                    <Badge tone="neutral">
                      no outcome yet:{" "}
                      {cohort.recorded_outcomes.without_outcome_record}
                    </Badge>
                  )}
                </div>
                <p>
                  Effectiveness{" "}
                  <Badge
                    tone={
                      TRUTH_TONE[cohort.effectiveness_aggregate.truth_level] ??
                      "neutral"
                    }
                  >
                    {cohort.effectiveness_aggregate.truth_level}
                  </Badge>{" "}
                  {cohort.effectiveness_aggregate.value != null
                    ? `mean ${fmtNum(cohort.effectiveness_aggregate.value)} over ${cohort.effectiveness_aggregate.count}`
                    : (cohort.effectiveness_aggregate.reason ?? "unknown")}
                </p>
                <p className="text-faint">
                  attribution supported/associated/unknown:{" "}
                  {cohort.attribution_summary.SUPPORTED ?? 0}/
                  {cohort.attribution_summary.ASSOCIATED ?? 0}/
                  {cohort.attribution_summary.UNKNOWN ?? 0}
                </p>
                <div className="flex flex-wrap gap-1">
                  {Object.keys(cohort.honesty)
                    .filter((k) => cohort.honesty[k])
                    .map((k) => (
                      <Badge key={k} tone="neutral">
                        {k.replaceAll("_", " ")}
                      </Badge>
                    ))}
                </div>
              </div>
            )}
          </Card>

          <Card
            title="Compare decisions"
            subtitle="4H.6: neutral side-by-side evidence for 2-5 decisions. The system presents evidence; humans judge. No winner, no score."
          >
            <div className="space-y-2">
              <input
                value={compareIds}
                onChange={(e) => setCompareIds(e.target.value)}
                placeholder="decision ids, comma separated (2-5)"
                className="w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-[12px] text-ink outline-none focus:border-brand"
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={runDecisionCompare}
                disabled={comparePerfBusy}
              >
                {comparePerfBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <GitCompareArrows className="h-3.5 w-3.5" />
                )}
                Compare side by side
              </Button>
              {comparison && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[12px]">
                    <thead>
                      <tr className="text-faint">
                        <th className="pr-3 py-1 font-medium">dimension</th>
                        {comparison.columns.map((c) => (
                          <th
                            key={c.decision_id}
                            className="pr-3 py-1 font-medium"
                          >
                            {c.title}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="text-muted">
                      {(
                        [
                          [
                            "outcome",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) =>
                              `${c.outcome.outcome_kind ?? "none"} (${c.outcome.truth})`,
                          ],
                          [
                            "effectiveness (recorded)",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) => fmtNum(c.recorded_effectiveness),
                          ],
                          [
                            "execution",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) =>
                              `${c.execution.actions} actions · ${c.execution.evidence_events} events`,
                          ],
                          [
                            "measured",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) =>
                              `${c.measured.linked_metrics} metrics · ${c.measured.derived_measurements} derived`,
                          ],
                          [
                            "attribution S/A/U",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) =>
                              `${c.attribution_summary.SUPPORTED ?? 0}/${c.attribution_summary.ASSOCIATED ?? 0}/${c.attribution_summary.UNKNOWN ?? 0}`,
                          ],
                          [
                            "unknowns",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) => String(c.unknowns.count),
                          ],
                          [
                            "anchor",
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) =>
                              `${c.anchor ? timeAgo(c.anchor) : "—"} (${c.anchor_basis})`,
                          ],
                        ] as Array<
                          [
                            string,
                            (
                              c: CompanyPerformanceComparisonResponse["columns"][number],
                            ) => string,
                          ]
                        >
                      ).map(([label, fn]) => (
                        <tr key={label} className="border-t border-line/60">
                          <td className="pr-3 py-1 text-faint">{label}</td>
                          {comparison.columns.map((c) => (
                            <td key={c.decision_id} className="pr-3 py-1">
                              {fn(c)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {comparison.comparison.not_found.length > 0 && (
                    <p className="mt-1 text-[11px] text-faint">
                      not found: {comparison.comparison.not_found.join(", ")}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {Object.keys(comparison.honesty)
                      .filter((k) => comparison.honesty[k])
                      .map((k) => (
                        <Badge key={k} tone="neutral">
                          {k.replaceAll("_", " ")}
                        </Badge>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Advisory only"
            subtitle="The company layer never executes anything."
          >
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <CircleDashed className="h-3.5 w-3.5 shrink-0 text-faint" />
              The company view composes the canonical systems for humans —
              decisions are recorded, never made, by the platform.
            </div>
          </Card>
        </div>
      </div>

      {actionError && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">
          {actionError}
        </p>
      )}
      {error && !loading && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
