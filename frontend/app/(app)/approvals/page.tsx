"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  Clock,
  FileCheck2,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import {
  cancelApproval,
  createApproval,
  decideApproval,
  getApprovalStats,
  listApprovals,
  listEmployees,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Approval, EmployeeSummary } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate, titleCase } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

const APPROVAL_TYPES = [
  "project",
  "task",
  "leave",
  "purchase",
  "budget",
  "expense",
  "document",
  "release",
  "meeting",
  "other",
];
const STATUSES = ["pending", "approved", "rejected", "cancelled"];

export default function ApprovalsPage() {
  return (
    <Suspense fallback={null}>
      <ApprovalsContent />
    </Suspense>
  );
}

function ApprovalsContent() {
  const params = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.APPROVALS_MANAGE);

  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState(params.get("status") ?? "");
  const [type, setType] = useState("");

  const [requestOpen, setRequestOpen] = useState(false);
  const [deciding, setDeciding] = useState<Approval | null>(null);
  const [cancelling, setCancelling] = useState<Approval | null>(null);
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    approval_type: "task",
    title: "",
    description: "",
    approver_id: "",
    priority: "medium",
    due_at: "",
  });
  const [note, setNote] = useState("");

  const pendingCount = approvals.filter((a) => a.status === "pending").length;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [items, statsData, empList] = await Promise.all([
        listApprovals({
          status: status || undefined,
          approval_type: type || undefined,
        }),
        getApprovalStats(),
        listEmployees({ page_size: 200 }),
      ]);
      setApprovals(items);
      setStats(statsData as Record<string, number>);
      setEmployees(empList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load approvals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, type]);

  const statCards = useMemo(() => {
    return [
      {
        label: "Total requests",
        value: stats.total ?? approvals.length,
        icon: FileCheck2,
      },
      { label: "Pending", value: stats.pending ?? pendingCount, icon: Clock },
      { label: "Approved", value: stats.approved ?? 0, icon: CheckCircle2 },
      { label: "Rejected", value: stats.rejected ?? 0, icon: XCircle },
      {
        label: "Approval rate",
        value: `${Math.round((stats.approval_rate ?? 0) * 100)}%`,
        icon: ShieldAlert,
      },
    ];
  }, [stats, approvals.length, pendingCount]);

  async function handleCreate() {
    if (!form.title.trim()) return toastError("Title is required");
    if (!form.approver_id) return toastError("Choose an approver");
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        approval_type: form.approval_type,
        title: form.title.trim(),
        description: form.description.trim() || undefined,
        approver_id: form.approver_id,
        priority: form.priority,
      };
      if (form.due_at) payload.due_at = new Date(form.due_at).toISOString();
      await createApproval(payload);
      toastSuccess("Approval requested");
      setRequestOpen(false);
      setForm({
        approval_type: "task",
        title: "",
        description: "",
        approver_id: "",
        priority: "medium",
        due_at: "",
      });
      await load();
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "Unable to request approval",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleDecide(decision: "approved" | "rejected") {
    if (!deciding) return;
    setBusy(true);
    try {
      await decideApproval(deciding.id, decision, note.trim() || undefined);
      toastSuccess(`${deciding.title} ${decision}`);
      setDeciding(null);
      setNote("");
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to decide");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!cancelling) return;
    setBusy(true);
    try {
      await cancelApproval(cancelling.id);
      toastSuccess(`${cancelling.title} cancelled`);
      setCancelling(null);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to cancel");
    } finally {
      setBusy(false);
    }
  }

  const statusTone: Record<string, string> = {
    pending: "warning",
    approved: "success",
    rejected: "danger",
    cancelled: "neutral",
  };

  if (loading && approvals.length === 0)
    return <Spinner label="Loading approvals…" />;
  if (error)
    return (
      <ErrorState
        title="Approvals unavailable"
        message={error}
        onRetry={load}
      />
    );

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <PageHeader
        title="Approvals"
        description="Requests routed for sign-off — decided here, every step notified and audited."
        actions={
          canManage ? (
            <Button onClick={() => setRequestOpen(true)}>
              <FileCheck2 className="h-4 w-4" /> Request approval
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {statCards.map(({ label, value, icon: Icon }) => (
          <Card key={label} className="flex items-center gap-3 p-4">
            <div className="rounded-lg bg-canvas p-2">
              <Icon className="h-4 w-4 text-accent" />
            </div>
            <div>
              <div className="text-lg font-semibold text-ink">{value}</div>
              <div className="text-xs text-faint">{label}</div>
            </div>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {["", ...STATUSES].map((s) => (
            <button
              key={s || "all"}
              onClick={() => setStatus(s)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                status === s
                  ? "bg-accent text-white"
                  : "text-faint hover:bg-canvas hover:text-ink"
              }`}
            >
              {s ? titleCase(s) : "All"}
            </button>
          ))}
        </div>
        <Select
          aria-label="Approval type"
          value={type}
          onChange={(event) => setType(event.target.value)}
          placeholder="All types"
          className="w-44"
          options={APPROVAL_TYPES.map((t) => ({
            value: t,
            label: titleCase(t),
          }))}
        />
      </div>

      {approvals.length === 0 ? (
        <EmptyState
          title="No approvals here"
          description={
            canManage
              ? "Request a sign-off and it will appear in this queue."
              : "Nothing routed to you yet."
          }
        />
      ) : (
        <div className="space-y-2">
          {approvals.map((approval) => (
            <Card
              key={approval.id}
              className="flex flex-wrap items-center justify-between gap-4 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink">{approval.title}</span>
                  <Badge tone="neutral">
                    {titleCase(approval.approval_type)}
                  </Badge>
                  <Badge
                    tone={
                      statusTone[approval.status] as
                        "success" | "warning" | "danger" | "neutral"
                    }
                  >
                    {titleCase(approval.status)}
                  </Badge>
                  {approval.priority !== "medium" && (
                    <Badge
                      tone={
                        approval.priority === "high" ||
                        approval.priority === "critical"
                          ? "danger"
                          : "warning"
                      }
                    >
                      {titleCase(approval.priority)} priority
                    </Badge>
                  )}
                </div>
                {approval.description && (
                  <p className="mt-1 text-sm text-ink/70">
                    {approval.description}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-faint">
                  <span>
                    {approval.requester_name ?? "—"} →{" "}
                    {approval.approver_name ?? "unassigned"}
                  </span>
                  {approval.due_at && (
                    <span>Due {formatDate(approval.due_at)}</span>
                  )}
                  {approval.decided_at && (
                    <span>
                      {approval.status === "approved"
                        ? "Approved"
                        : approval.status === "rejected"
                          ? "Rejected"
                          : "Decided"}{" "}
                      {formatDate(approval.decided_at)}
                    </span>
                  )}
                  {approval.decision_note && (
                    <span className="italic">“{approval.decision_note}”</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {approval.status === "pending" && (
                  <>
                    {canManage && (
                      <>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setDeciding(approval)}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => setDeciding(approval)}
                        >
                          Reject
                        </Button>
                      </>
                    )}
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setCancelling(approval)}
                    >
                      Cancel
                    </Button>
                  </>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={requestOpen}
        onClose={() => setRequestOpen(false)}
        title="Request approval"
        description="The approver is notified immediately and can decide from this queue."
        footer={
          <>
            <Button variant="secondary" onClick={() => setRequestOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={busy}>
              {busy ? "Requesting…" : "Request approval"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            aria-label="Approval type"
            label="Type"
            value={form.approval_type}
            onChange={(event) =>
              setForm({ ...form, approval_type: event.target.value })
            }
            options={APPROVAL_TYPES.map((t) => ({
              value: t,
              label: titleCase(t),
            }))}
          />
          <div>
            <Input
              label="Title"
              name="approval-title"
              value={form.title}
              onChange={(event) =>
                setForm({ ...form, title: event.target.value })
              }
              placeholder="What needs approval?"
            />
          </div>
          <div>
            <label className="label">Description</label>
            <Textarea
              aria-label="Context for the approver"
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
              rows={3}
              placeholder="Context for the approver…"
            />
          </div>
          <Select
            aria-label="Approver"
            label="Approver"
            value={form.approver_id}
            onChange={(event) =>
              setForm({ ...form, approver_id: event.target.value })
            }
            placeholder="Choose who decides"
            options={employees.map((e) => ({
              value: e.id,
              label: e.full_name,
            }))}
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              aria-label="Priority"
              label="Priority"
              value={form.priority}
              onChange={(event) =>
                setForm({ ...form, priority: event.target.value })
              }
              options={["low", "medium", "high", "critical"].map((p) => ({
                value: p,
                label: titleCase(p),
              }))}
            />
            <div>
              <Input
                label="Due by"
                name="approval-due"
                type="date"
                value={form.due_at}
                onChange={(event) =>
                  setForm({ ...form, due_at: event.target.value })
                }
              />
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={deciding !== null}
        onClose={() => setDeciding(null)}
        title={`Decide: ${deciding?.title ?? ""}`}
        description="Your decision notifies the requester and is recorded in the audit trail."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeciding(null)}>
              Close
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleDecide("approved")}
              disabled={busy}
            >
              Approve
            </Button>
            <Button
              variant="danger"
              onClick={() => handleDecide("rejected")}
              disabled={busy}
            >
              Reject
            </Button>
          </>
        }
      >
        <div>
          <label className="label">Decision note</label>
          <Textarea
            aria-label="Decision note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            placeholder="Optional note for the requester…"
          />
        </div>
      </Modal>

      <Modal
        open={cancelling !== null}
        onClose={() => setCancelling(null)}
        title="Cancel approval"
        description="A cancelled request can no longer be decided."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancelling(null)}>
              Keep it
            </Button>
            <Button variant="danger" onClick={handleCancel} disabled={busy}>
              {busy ? "Cancelling…" : "Cancel request"}
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink/70">
          Cancel{" "}
          <span className="font-medium text-ink">{cancelling?.title}</span>?
        </p>
      </Modal>
    </div>
  );
}
