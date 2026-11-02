"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Clock,
  Flag,
  Hammer,
  ListPlus,
  Lock,
  Play,
  RefreshCw,
  Target,
  ThumbsDown,
  ThumbsUp,
  Undo2,
  UserPlus,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import { useAuth } from "@/hooks/useAuth";
import {
  brainKnowledgeActionCenter,
  brainKnowledgeActionDetail,
  brainKnowledgeActionEvaluate,
  brainKnowledgeActionOutcome,
  brainKnowledgeActionOutcomeIntelligence,
  brainKnowledgeActionPropose,
  brainKnowledgeActionTransition,
  brainKnowledgeRecommendations,
  getMyEmployee,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { classNames, formatDateTime, timeAgo } from "@/lib/utils";
import type {
  CompanyAction,
  CompanyActionCenterResponse,
  CompanyActionDetailResponse,
  CompanyActionOutcomeIntelligence,
  KnowledgeIntelRecommendation,
} from "@/types";

const ACTION_TYPES = [
  "task",
  "decision",
  "communication",
  "knowledge",
  "meeting",
  "project",
] as const;

const STATE_TONE: Record<
  string,
  "neutral" | "brand" | "success" | "warning" | "danger"
> = {
  proposed: "neutral",
  validating: "brand",
  awaiting_approval: "warning",
  approved: "brand",
  ready: "brand",
  in_progress: "brand",
  blocked: "danger",
  completed: "success",
  verified: "success",
  rejected: "neutral",
  cancelled: "neutral",
  expired: "neutral",
  failed: "danger",
  superseded: "neutral",
};

const STATE_LABEL: Record<string, string> = {
  proposed: "Proposed",
  validating: "Validating",
  awaiting_approval: "Awaiting approval",
  approved: "Approved",
  ready: "Ready",
  in_progress: "In progress",
  blocked: "Blocked",
  completed: "Completed",
  verified: "Verified",
  rejected: "Rejected",
  cancelled: "Cancelled",
  expired: "Expired",
  failed: "Failed",
  superseded: "Superseded",
};

function stateLabel(state: string): string {
  return STATE_LABEL[state] ?? state.replaceAll("_", " ");
}

function stateTone(state: string) {
  return STATE_TONE[state] ?? "neutral";
}

export default function KnowledgeActionCenterPage() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.BRAIN_MANAGE);

  const [data, setData] = useState<CompanyActionCenterResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);
  const [filters, setFilters] = useState<{
    state: string;
    action_type: string;
    view: "all" | "mine" | "attention" | "blocked" | "overdue" | "escalated";
  }>({ state: "", action_type: "", view: "all" });
  const [intel, setIntel] = useState<CompanyActionOutcomeIntelligence | null>(
    null,
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<CompanyActionDetailResponse | null>(
    null,
  );
  const [detailBusy, setDetailBusy] = useState(false);
  const [runBusy, setRunBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [showPropose, setShowPropose] = useState(false);
  const [proposals, setProposals] = useState<KnowledgeIntelRecommendation[]>(
    [],
  );
  const [propose, setPropose] = useState({
    action_type: "task",
    title: "",
    description: "",
    source_problem: "",
    risk: "medium",
    recommendation_id: "",
    scope_type: "org",
    scope_id: "",
    due_at: "",
  });

  const params = useMemo(() => {
    const query: Record<string, string | boolean | number> = { limit: 60 };
    if (filters.state) query.state = filters.state;
    if (filters.action_type) query.action_type = filters.action_type;
    if (filters.view === "mine") query.mine = true;
    if (filters.view === "attention") query.attention = true;
    if (filters.view === "blocked") query.blocked_only = true;
    if (filters.view === "overdue") query.overdue_only = true;
    if (filters.view === "escalated") query.escalated_only = true;
    return query;
  }, [filters]);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [center, outcomeIntel] = await Promise.all([
        brainKnowledgeActionCenter(params),
        brainKnowledgeActionOutcomeIntelligence().catch(() => null),
      ]);
      setData(center);
      setIntel(outcomeIntel);
    } catch {
      setData(null);
    } finally {
      setBusy(false);
    }
  }, [params]);

  useEffect(() => {
    void load();
    getMyEmployee()
      .then((employee) => setMyEmployeeId(employee.id))
      .catch(() => undefined);
  }, [load]);

  const loadProposals = useCallback(async () => {
    if (!canManage) return;
    try {
      const result = await brainKnowledgeRecommendations({ limit: 50 });
      setProposals(result.recommendations);
    } catch {
      setProposals([]);
    }
  }, [canManage]);

  const openDetail = useCallback(
    async (actionId: string) => {
      setDetailBusy(true);
      setExpanded(expanded === actionId ? null : actionId);
      try {
        const result = await brainKnowledgeActionDetail(actionId);
        setDetail(result);
      } catch {
        setDetail(null);
      } finally {
        setDetailBusy(false);
      }
    },
    [expanded],
  );

  const run = useCallback(
    async (
      actionId: string,
      transition: string,
      extra?: Record<string, string>,
    ) => {
      if (!canManage || runBusy) return;
      setRunBusy(actionId);
      setError(null);
      setNotice(null);
      try {
        const payload: {
          transition: string;
          note?: string | null;
          assignee_id?: string | null;
        } = { transition };
        if (note.trim() && transition !== "assign") payload.note = note.trim();
        const result = await brainKnowledgeActionTransition(actionId, {
          ...payload,
          ...extra,
        });
        setNotice(
          `${stateLabel(result.state)} — ${result.attention_reasons.join(", ") || "no attention flags"}`,
        );
        setNote("");
        await Promise.all([
          load(),
          expanded === actionId ? openDetail(actionId) : Promise.resolve(),
        ]);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : `transition ${transition} failed`,
        );
      } finally {
        setRunBusy(null);
      }
    },
    [canManage, expanded, load, note, openDetail, runBusy],
  );

  const recordOutcome = useCallback(
    async (actionId: string) => {
      if (!canManage || runBusy) return;
      setRunBusy(actionId);
      try {
        await brainKnowledgeActionOutcome(actionId, {
          outcome_type: note.trim().toLowerCase().startsWith("fail")
            ? "failed"
            : "success",
          verdict: note.trim() || null,
          effectiveness: note.trim().toLowerCase().startsWith("fail")
            ? 0.2
            : 0.9,
          notes: note.trim() || null,
        });
        setNotice(
          "Outcome recorded — the result loops back into company intelligence",
        );
        setNote("");
        await Promise.all([load(), openDetail(actionId)]);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "outcome recording failed",
        );
      } finally {
        setRunBusy(null);
      }
    },
    [canManage, load, note, openDetail, runBusy],
  );

  const evaluate = useCallback(async () => {
    setBusy(true);
    try {
      const result = await brainKnowledgeActionEvaluate();
      setNotice(
        `Operational pass: ${result.evaluated} evaluated · ${result.expired} expired · ${result.escalated} escalated · ${result.auto_completed} reflected`,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "evaluate failed");
    } finally {
      setBusy(false);
    }
  }, [load]);

  const proposeAction = useCallback(async () => {
    if (!canManage || !propose.title.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const payload: {
        action_type: string;
        title: string;
        risk: string;
        description?: string;
        source_problem?: string;
        source_recommendation_id?: string;
        scope_type?: string;
        scope_id?: string;
        due_at?: string;
      } = {
        action_type: propose.action_type,
        title: propose.title.trim(),
        risk: propose.risk,
      };
      if (propose.description.trim())
        payload.description = propose.description.trim();
      if (propose.source_problem.trim())
        payload.source_problem = propose.source_problem.trim();
      if (propose.recommendation_id)
        payload.source_recommendation_id = propose.recommendation_id;
      if (propose.scope_type !== "org") {
        payload.scope_type = propose.scope_type;
        if (propose.scope_id.trim()) payload.scope_id = propose.scope_id.trim();
      }
      if (propose.due_at)
        payload.due_at = new Date(propose.due_at).toISOString();
      const result = await brainKnowledgeActionPropose(payload);
      setNotice(
        result.deduplicated
          ? `Already tracked — replayed onto the existing action (${result.state})`
          : `Action proposed: ${stateLabel(result.state)} · ${result.attention_reasons.join(", ") || "no flags"}`,
      );
      setPropose({
        ...propose,
        title: "",
        description: "",
        source_problem: "",
      });
      setShowPropose(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "proposal failed");
    } finally {
      setBusy(false);
    }
  }, [canManage, load, propose]);

  const rows = data?.items ?? [];
  const stats = data?.stats;

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          One governed surface for every company action — proposed from
          knowledge, routed into the existing operating systems, and tracked to
          a measured outcome. Nothing is invented, nothing is deleted.
        </p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void evaluate()}
            disabled={busy}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`}
            />{" "}
            Evaluate
          </Button>
          {canManage && (
            <Button
              size="sm"
              onClick={() => {
                setShowPropose((v) => !v);
                if (!proposals.length) void loadProposals();
              }}
            >
              <ListPlus className="h-3.5 w-3.5" />{" "}
              {showPropose ? "Hide propose" : "Propose action"}
            </Button>
          )}
        </div>
      </div>

      {!canManage && (
        <Card>
          <p className="text-[13px] text-muted">
            You can view the action center. Manage access (
            <span className="font-mono">brain:manage</span>) is required to
            propose, approve, transition or record outcomes.
          </p>
        </Card>
      )}

      {showPropose && canManage && (
        <Card bodyClassName="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-brand" />
            <p className="text-sm font-semibold text-ink">
              Propose a governed company action
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <Input
                placeholder="Title — e.g. Escalate the budget conflict"
                value={propose.title}
                onChange={(e) =>
                  setPropose({ ...propose, title: e.target.value })
                }
              />
            </div>
            <div className="md:col-span-2">
              <Input
                placeholder="Why now? (source problem — optionally leave empty to inherit from a recommendation)"
                value={propose.source_problem}
                onChange={(e) =>
                  setPropose({ ...propose, source_problem: e.target.value })
                }
              />
            </div>
            <div className="md:col-span-2">
              <Textarea
                placeholder="Description / expected outcome"
                value={propose.description}
                onChange={(e) =>
                  setPropose({ ...propose, description: e.target.value })
                }
              />
            </div>
            <select
              value={propose.action_type}
              onChange={(e) =>
                setPropose({ ...propose, action_type: e.target.value })
              }
              className="rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink outline-none focus:border-brand"
            >
              {ACTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <select
              value={propose.risk}
              onChange={(e) => setPropose({ ...propose, risk: e.target.value })}
              className="rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink outline-none focus:border-brand"
            >
              <option value="low">low risk · auto-approves</option>
              <option value="medium">medium risk · needs approval</option>
              <option value="high">high risk · mandates approval</option>
            </select>
            {proposals.length > 0 && (
              <select
                value={propose.recommendation_id}
                onChange={(e) =>
                  setPropose({ ...propose, recommendation_id: e.target.value })
                }
                className="rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink outline-none focus:border-brand"
              >
                <option value="">No source recommendation</option>
                {proposals.slice(0, 40).map((rec) => (
                  <option key={rec.id} value={rec.id}>
                    {rec.kind}: {rec.reason.slice(0, 60)}
                  </option>
                ))}
              </select>
            )}
            <select
              value={propose.scope_type}
              onChange={(e) =>
                setPropose({ ...propose, scope_type: e.target.value })
              }
              className="rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink outline-none focus:border-brand"
            >
              <option value="org">org scope</option>
              <option value="project">project scope</option>
            </select>
            {propose.scope_type !== "org" && (
              <Input
                placeholder="Project id (scope)"
                value={propose.scope_id}
                onChange={(e) =>
                  setPropose({ ...propose, scope_id: e.target.value })
                }
              />
            )}
            <Input
              type="datetime-local"
              value={propose.due_at}
              onChange={(e) =>
                setPropose({ ...propose, due_at: e.target.value })
              }
            />
            <Button onClick={() => void proposeAction()} disabled={busy}>
              <ListPlus className="h-3.5 w-3.5" /> Propose
            </Button>
          </div>
        </Card>
      )}

      {error && (
        <Card>
          <p className="text-[13px] text-danger">{error}</p>
        </Card>
      )}
      {notice && (
        <Card>
          <p className="text-[13px] text-success">{notice}</p>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-4">
        <CountStat label="Open actions" value={stats?.open ?? 0} />
        <CountStat
          label="Awaiting approval"
          value={stats?.by_state?.awaiting_approval ?? 0}
        />
        <CountStat label="Blocked" value={stats?.by_state?.blocked ?? 0} />
        <CountStat
          label="Completed"
          value={
            (stats?.by_state?.completed ?? 0) + (stats?.by_state?.verified ?? 0)
          }
        />
      </div>

      {intel && intel.total > 0 && (
        <Card bodyClassName="p-4">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px]">
            <span className="font-semibold uppercase tracking-wide text-faint">
              Action effectiveness
            </span>
            <span>outcomes: {intel.total}</span>
            <span className="text-success">
              success rate {(intel.success_rate * 100).toFixed(0)}%
            </span>
            <span>
              avg effectiveness {(intel.avg_effectiveness * 100).toFixed(0)}%
            </span>
            {intel.by_action_type.slice(0, 6).map((row) => (
              <span key={row.key} className="text-muted">
                {row.key}: {row.success}/{row.total}
              </span>
            ))}
          </div>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={filters.view}
          onChange={(e) =>
            setFilters({
              ...filters,
              view: e.target.value as typeof filters.view,
            })
          }
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
        >
          <option value="all">All views</option>
          <option value="attention">Needs attention</option>
          <option value="mine">Mine</option>
          <option value="blocked">Blocked</option>
          <option value="overdue">Overdue</option>
          <option value="escalated">Escalated</option>
        </select>
        <select
          value={filters.state}
          onChange={(e) => setFilters({ ...filters, state: e.target.value })}
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
        >
          <option value="">Any state</option>
          {Object.entries(STATE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={filters.action_type}
          onChange={(e) =>
            setFilters({ ...filters, action_type: e.target.value })
          }
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
        >
          <option value="">Any type</option>
          {ACTION_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <span className="ml-auto text-[11px] text-faint">
          {data?.scope === "org" ? "org-wide view" : "scoped view"} ·{" "}
          {data?.total ?? 0} actions · {data?.limit ?? 0} per page
        </span>
      </div>

      {busy && !data ? (
        <Card>
          <div className="flex items-center justify-center py-10 text-sm text-faint">
            Loading the action center…
          </div>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={Target}
            title="No actions here"
            description="Propose an action from a recommendation, or ask the Ask surface 'what needs my attention' — the action center stays empty until the knowledge layer has something worth acting on."
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((action) => (
            <Card key={action.id} bodyClassName="p-0">
              <div className="px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={stateTone(action.state)}>
                        {stateLabel(action.state)}
                      </Badge>
                      <Badge tone="neutral">{action.action_type}</Badge>
                      <Badge
                        tone={
                          action.risk === "high"
                            ? "danger"
                            : action.risk === "medium"
                              ? "warning"
                              : "success"
                        }
                      >
                        {action.risk} risk
                      </Badge>
                      {action.approval_required && (
                        <Badge tone="warning">
                          <Lock className="h-3 w-3" /> approval
                        </Badge>
                      )}
                      {action.overdue && (
                        <Badge tone="danger">
                          <Clock className="h-3 w-3" /> overdue
                        </Badge>
                      )}
                      {action.escalation_level > 0 && (
                        <Badge tone="danger">
                          <AlertTriangle className="h-3 w-3" /> escalated
                        </Badge>
                      )}
                      {action.attention_reasons.length > 0 &&
                        action.attention_reasons.map((reason) => (
                          <Badge key={reason} tone="warning">
                            {reason}
                          </Badge>
                        ))}
                    </div>
                    <p className="mt-2 text-sm font-semibold text-ink">
                      {action.title}
                    </p>
                    <p className="mt-1 text-[12px] leading-relaxed text-muted">
                      {action.source_problem ??
                        action.why ??
                        action.description}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[11px] text-faint">
                      {action.scope_type !== "org" && (
                        <span>
                          scope {action.scope_type}:{action.scope_id}
                        </span>
                      )}
                      {action.assignee_id && (
                        <span>assignee {action.assignee_id}</span>
                      )}
                      {action.due_at && (
                        <span>due {formatDateTime(action.due_at)}</span>
                      )}
                      {action.target_type && action.target_id && (
                        <span>
                          routed → {action.target_type} {action.target_id}
                        </span>
                      )}
                      {action.dependencies.length > 0 && (
                        <span>{action.dependencies.length} dependencies</span>
                      )}
                      <span>
                        priority {action.priority_score.toFixed(0)} · updated{" "}
                        {timeAgo(action.updated_at)}
                      </span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void openDetail(action.id)}
                    disabled={detailBusy}
                  >
                    {expanded === action.id ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                    {expanded === action.id ? "Close" : "Details"}
                  </Button>
                </div>

                {canManage && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
                    {action.state === "awaiting_approval" && (
                      <>
                        <RunButton
                          label="Approve"
                          icon={<ThumbsUp className="h-3.5 w-3.5" />}
                          primary
                          onClick={() =>
                            void run(
                              action.id,
                              "approve",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                        <RunButton
                          label="Reject"
                          icon={<ThumbsDown className="h-3.5 w-3.5" />}
                          onClick={() =>
                            void run(
                              action.id,
                              "reject",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                      </>
                    )}
                    {action.state === "approved" && (
                      <RunButton
                        label="Ready"
                        icon={<CircleDashed className="h-3.5 w-3.5" />}
                        onClick={() => void run(action.id, "ready")}
                        busy={runBusy === action.id}
                      />
                    )}
                    {["approved", "ready"].includes(action.state) && (
                      <RunButton
                        label="Assign"
                        icon={<UserPlus className="h-3.5 w-3.5" />}
                        onClick={() =>
                          void run(action.id, "assign", {
                            assignee_id: myEmployeeId ?? "me",
                          })
                        }
                        busy={runBusy === action.id}
                      />
                    )}
                    {["ready", "approved"].includes(action.state) && (
                      <RunButton
                        label="Start"
                        icon={<Play className="h-3.5 w-3.5" />}
                        onClick={() =>
                          void run(
                            action.id,
                            "start",
                            note.trim() ? { note: note.trim() } : {},
                          )
                        }
                        busy={runBusy === action.id}
                      />
                    )}
                    {action.state === "in_progress" && (
                      <>
                        <RunButton
                          label="Block"
                          icon={<Hammer className="h-3.5 w-3.5" />}
                          onClick={() =>
                            void run(
                              action.id,
                              "block",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                        <RunButton
                          label="Complete"
                          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                          primary
                          onClick={() =>
                            void run(
                              action.id,
                              "complete",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                      </>
                    )}
                    {action.state === "blocked" && (
                      <RunButton
                        label="Unblock"
                        icon={<Undo2 className="h-3.5 w-3.5" />}
                        onClick={() =>
                          void run(
                            action.id,
                            "unblock",
                            note.trim() ? { note: note.trim() } : {},
                          )
                        }
                        busy={runBusy === action.id}
                      />
                    )}
                    {action.state === "completed" && (
                      <>
                        <RunButton
                          label="Verify"
                          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                          primary
                          onClick={() =>
                            void run(
                              action.id,
                              "verify",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                        <RunButton
                          label="Record outcome"
                          icon={<Flag className="h-3.5 w-3.5" />}
                          onClick={() => void recordOutcome(action.id)}
                          busy={runBusy === action.id}
                        />
                      </>
                    )}
                    {![
                      "completed",
                      "verified",
                      "rejected",
                      "cancelled",
                      "expired",
                      "failed",
                      "superseded",
                    ].includes(action.state) && (
                      <>
                        <RunButton
                          label="Fail"
                          icon={<XCircle className="h-3.5 w-3.5" />}
                          onClick={() =>
                            void run(
                              action.id,
                              "fail",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                        <RunButton
                          label="Cancel"
                          icon={<XCircle className="h-3.5 w-3.5" />}
                          onClick={() =>
                            void run(
                              action.id,
                              "cancel",
                              note.trim() ? { note: note.trim() } : {},
                            )
                          }
                          busy={runBusy === action.id}
                        />
                      </>
                    )}
                    {["awaiting_approval", "approved"].includes(
                      action.state,
                    ) && (
                      <RunButton
                        label="Expire"
                        icon={<Clock className="h-3.5 w-3.5" />}
                        onClick={() =>
                          void run(
                            action.id,
                            "expire",
                            note.trim() ? { note: note.trim() } : {},
                          )
                        }
                        busy={runBusy === action.id}
                      />
                    )}
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Note for this transition (verification requires one)"
                      className="min-w-[200px] flex-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
                    />
                  </div>
                )}
              </div>

              {expanded === action.id && (
                <div className="border-t border-line px-5 py-4">
                  <ActionDetail
                    detail={detail}
                    actionId={action.id}
                    canManage={canManage}
                    onTransition={run}
                    onOutcome={recordOutcome}
                    note={note}
                  />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function CountStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <p
        className={classNames(
          "text-xl font-bold",
          value > 0 ? "text-ink" : "text-faint",
        )}
      >
        {value}
      </p>
      <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-faint">
        {label}
      </p>
    </div>
  );
}

function RunButton({
  label,
  icon,
  onClick,
  busy,
  primary,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  busy: boolean;
  primary?: boolean;
}) {
  return (
    <Button
      size="sm"
      variant={primary ? "primary" : "secondary"}
      onClick={onClick}
      disabled={busy}
    >
      {icon} {label}
    </Button>
  );
}

function ActionDetail({
  detail,
  actionId,
  canManage,
  onTransition,
  onOutcome,
  note,
}: {
  detail: CompanyActionDetailResponse | null;
  actionId: string;
  canManage: boolean;
  onTransition: (
    id: string,
    transition: string,
    extra?: Record<string, string>,
  ) => Promise<void>;
  onOutcome: (id: string) => Promise<void>;
  note: string;
}) {
  if (!detail) {
    return <p className="text-xs text-faint">Loading the action lineage…</p>;
  }
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
            Why this action exists
          </p>
          <p className="text-[12px] leading-relaxed text-muted">
            {detail.why ?? "No recorded reason — a plain operational action."}
          </p>
          {detail.source_problem && (
            <p className="mt-1 text-[12px] text-muted">
              <span className="text-faint">Source problem: </span>
              {detail.source_problem}
            </p>
          )}
          {detail.source_claim_ids.length > 0 && (
            <p className="mt-1 text-[11px] text-faint">
              evidence claims: {detail.source_claim_ids.length} cited
            </p>
          )}
          {detail.source_recommendation && (
            <div className="mt-2 rounded-lg border border-line bg-surface p-3">
              <p className="text-[11px] font-semibold text-brand">
                {detail.source_recommendation.kind} recommendation
              </p>
              <p className="mt-0.5 text-[11px] text-muted">
                {detail.source_recommendation.reason}
              </p>
              <p className="mt-0.5 text-[10px] text-faint">
                confidence{" "}
                {(detail.source_recommendation.confidence * 100).toFixed(0)}% ·{" "}
                {detail.source_recommendation.risk} risk
              </p>
            </div>
          )}
          {detail.source_insight && (
            <div className="mt-2 rounded-lg border border-line bg-surface p-3">
              <p className="text-[11px] font-semibold text-brand">
                {detail.source_insight.kind} insight
              </p>
              <p className="mt-0.5 text-[11px] text-muted">
                {detail.source_insight.title}
              </p>
            </div>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
            Dependencies
          </p>
          {detail.dependencies.length === 0 ? (
            <p className="text-[11px] text-faint">none</p>
          ) : (
            <ul className="space-y-1">
              {detail.dependencies.map((dep) => (
                <li
                  key={dep.id}
                  className="flex items-center gap-2 text-[11px] text-muted"
                >
                  <span
                    className={dep.complete ? "text-success" : "text-warning"}
                  >
                    {dep.complete ? "✓" : "○"}
                  </span>
                  <span>{dep.title ?? dep.id}</span>
                  <Badge tone={dep.complete ? "success" : "warning"}>
                    {dep.state ?? "?"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          {detail.outcome && (
            <div className="mt-3 rounded-lg border border-line bg-surface p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                Outcome (the loop back)
              </p>
              <p className="mt-1 text-[12px] text-ink">
                {detail.outcome.outcome_type}
                <Badge
                  tone={
                    detail.outcome.outcome_type === "success"
                      ? "success"
                      : detail.outcome.outcome_type === "failed"
                        ? "danger"
                        : "warning"
                  }
                  className="ml-2"
                >
                  {(detail.outcome.effectiveness * 100).toFixed(0)}% effective
                </Badge>
              </p>
              {detail.outcome.verdict && (
                <p className="mt-0.5 text-[11px] text-muted">
                  “{detail.outcome.verdict}”
                </p>
              )}
              <p className="mt-0.5 text-[10px] text-faint">
                {detail.outcome.evidence.length} evidence ids · measured{" "}
                {formatDateTime(detail.outcome.measured_at)}
              </p>
            </div>
          )}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
          Audit trail (immutable)
        </p>
        <ol className="space-y-1">
          {detail.events.map((event, index) => (
            <li
              key={index}
              className="flex flex-wrap items-start gap-2 text-[11px] text-muted"
            >
              <Badge tone="neutral" className="shrink-0">
                {event.event}
              </Badge>
              <span className="text-faint">
                {formatDateTime(event.created_at)}
                {event.note ? ` · “${event.note}”` : ""}
                {event.details &&
                  ` · ${JSON.stringify(event.details).slice(0, 120)}`}
              </span>
            </li>
          ))}
        </ol>
      </div>

      {canManage && (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[11px] text-faint">
            Replay a transition or record an outcome here — every step stays on
            the record.
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              void onTransition(actionId, "assign", { assignee_id: "me" })
            }
            disabled={!Boolean(detail)}
          >
            Assign me
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void onOutcome(actionId)}
            disabled={!note.trim()}
          >
            Record outcome
          </Button>
        </div>
      )}
    </div>
  );
}
