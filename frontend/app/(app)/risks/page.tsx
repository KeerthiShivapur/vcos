"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  PencilLine,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";

import {
  closeRisk,
  createRisk,
  deleteRisk,
  listEmployees,
  listProjects,
  listRisks,
  updateRisk,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { EmployeeSummary, Project, Risk } from "@/types";
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

const RISK_STATUSES = [
  "identified",
  "assessing",
  "mitigating",
  "accepted",
  "monitoring",
  "closed",
];
const SEVERITIES = ["critical", "high", "medium", "low"];

export default function RisksPage() {
  return (
    <Suspense fallback={null}>
      <RisksContent />
    </Suspense>
  );
}

function RisksContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.RISKS_MANAGE);

  const [risks, setRisks] = useState<Risk[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");

  const [logOpen, setLogOpen] = useState(false);
  const [editing, setEditing] = useState<Risk | null>(null);
  const [deleting, setDeleting] = useState<Risk | null>(null);
  const [busy, setBusy] = useState(false);

  const emptyForm = {
    project_id: "",
    title: "",
    description: "",
    probability: "2",
    impact: "2",
    owner_id: "",
    mitigation: "",
    due_at: "",
  };
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [items, projectList, empList] = await Promise.all([
        listRisks({
          project_id: projectId || undefined,
          status: status || undefined,
          severity: severity || undefined,
        }),
        listProjects(),
        listEmployees({ page_size: 200 }),
      ]);
      setRisks(items);
      setProjects(projectList);
      setEmployees(empList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load risks");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, status, severity]);

  const summary = useMemo(() => {
    const open = risks.filter((r) => r.status !== "closed");
    return {
      open: open.length,
      critical: open.filter((r) => r.severity === "critical").length,
      high: open.filter((r) => r.severity === "high").length,
      avg: open.length
        ? Math.round(
            open.reduce((acc, r) => acc + (r.risk_score ?? 0), 0) / open.length,
          )
        : 0,
    };
  }, [risks]);

  const severityTone: Record<
    string,
    "danger" | "warning" | "neutral" | "success"
  > = {
    critical: "danger",
    high: "warning",
    medium: "neutral",
    low: "success",
  };

  function openCreate() {
    setForm(emptyForm);
    setLogOpen(true);
  }

  function openEdit(risk: Risk) {
    setEditing(risk);
    setForm({
      project_id: risk.project_id ?? "",
      title: risk.title,
      description: risk.description ?? "",
      probability: String(risk.probability),
      impact: String(risk.impact),
      owner_id: risk.owner_id ?? "",
      mitigation: risk.mitigation ?? "",
      due_at: risk.due_at ? risk.due_at.slice(0, 10) : "",
    });
  }

  async function handleSave() {
    if (!form.title.trim()) return toastError("Title is required");
    const probability = Math.min(5, Math.max(1, Number(form.probability) || 1));
    const impact = Math.min(5, Math.max(1, Number(form.impact) || 1));
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        project_id: form.project_id || undefined,
        title: form.title.trim(),
        description: form.description.trim() || undefined,
        probability,
        impact,
        owner_id: form.owner_id || undefined,
        mitigation: form.mitigation.trim() || undefined,
      };
      if (form.due_at)
        payload.due_at = new Date(`${form.due_at}T00:00:00`).toISOString();
      if (editing) {
        await updateRisk(editing.id, payload);
        toastSuccess("Risk updated");
        setEditing(null);
      } else {
        await createRisk(payload);
        toastSuccess("Risk logged");
        setLogOpen(false);
      }
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to save risk");
    } finally {
      setBusy(false);
    }
  }

  async function handleClose(risk: Risk) {
    try {
      await closeRisk(risk.id);
      toastSuccess(`${risk.title} closed`);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to close risk");
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setBusy(true);
    try {
      await deleteRisk(deleting.id);
      toastSuccess("Risk deleted");
      setDeleting(null);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete risk");
    } finally {
      setBusy(false);
    }
  }

  if (loading && risks.length === 0)
    return <Spinner label="Loading risk register…" />;
  if (error)
    return (
      <ErrorState
        title="Risk register unavailable"
        message={error}
        onRetry={load}
      />
    );

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <PageHeader
        title="Risk Register"
        description="Every open risk scored by probability × impact — feeding company health and executive briefs."
        actions={
          canManage ? (
            <Button onClick={openCreate}>
              <AlertTriangle className="h-4 w-4" /> Log risk
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: "Open risks", value: summary.open, icon: ShieldAlert },
          { label: "Critical", value: summary.critical, icon: XCircle },
          { label: "High", value: summary.high, icon: AlertTriangle },
          { label: "Avg open score", value: summary.avg, icon: ShieldCheck },
        ].map(({ label, value, icon: Icon }) => (
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
        <Select
          aria-label="Project"
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
          placeholder="All projects"
          className="w-52"
          options={projects.map((p) => ({ value: p.id, label: p.name }))}
        />
        <Select
          aria-label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          placeholder="All statuses"
          className="w-44"
          options={RISK_STATUSES.map((s) => ({
            value: s,
            label: titleCase(s),
          }))}
        />
        <Select
          aria-label="Severity"
          value={severity}
          onChange={(event) => setSeverity(event.target.value)}
          placeholder="All severities"
          className="w-40"
          options={SEVERITIES.map((s) => ({ value: s, label: titleCase(s) }))}
        />
      </div>

      {risks.length === 0 ? (
        <EmptyState
          title="No risks match"
          description={
            canManage
              ? "Log the first risk to start the register."
              : "Nothing to see here yet."
          }
        />
      ) : (
        <div className="space-y-2">
          {risks.map((risk) => (
            <Card
              key={risk.id}
              className="flex flex-wrap items-center justify-between gap-4 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink">{risk.title}</span>
                  <Badge tone={severityTone[risk.severity ?? ""] ?? "neutral"}>
                    {titleCase(risk.severity ?? "unknown")}
                  </Badge>
                  <Badge tone="neutral">
                    P{risk.probability} × I{risk.impact} = {risk.risk_score}
                  </Badge>
                  <Badge tone="neutral">{titleCase(risk.status)}</Badge>
                </div>
                {risk.description && (
                  <p className="mt-1 text-sm text-ink/70">{risk.description}</p>
                )}
                {risk.mitigation && (
                  <p className="mt-1 text-xs text-faint">
                    <span className="font-medium text-ink/60">Mitigation:</span>{" "}
                    {risk.mitigation}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-faint">
                  {risk.project_name && <span>{risk.project_name}</span>}
                  {risk.owner_name && <span>Owner: {risk.owner_name}</span>}
                  {risk.due_at && <span>Due {formatDate(risk.due_at)}</span>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {risk.status !== "closed" && canManage && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleClose(risk)}
                  >
                    Close
                  </Button>
                )}
                {canManage && (
                  <>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => openEdit(risk)}
                    >
                      <PencilLine className="h-3.5 w-3.5" /> Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      aria-label={`Delete ${risk.title}`}
                      onClick={() => setDeleting(risk)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={logOpen || editing !== null}
        onClose={() => {
          setLogOpen(false);
          setEditing(null);
        }}
        title={editing ? `Edit: ${editing.title}` : "Log risk"}
        description="Score 1–5 on probability and impact — the score updates automatically."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setLogOpen(false);
                setEditing(null);
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={busy}>
              {busy ? "Saving…" : editing ? "Save changes" : "Log risk"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            aria-label="Risk project"
            label="Project"
            value={form.project_id}
            onChange={(event) =>
              setForm({ ...form, project_id: event.target.value })
            }
            placeholder="Optional project context"
            options={projects.map((p) => ({ value: p.id, label: p.name }))}
          />
          <div>
            <Input
              label="Title"
              name="risk-title"
              value={form.title}
              onChange={(event) =>
                setForm({ ...form, title: event.target.value })
              }
              placeholder="What could go wrong?"
            />
          </div>
          <div>
            <label className="label">Description</label>
            <Textarea
              aria-label="Risk description"
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
              rows={3}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Input
                label="Probability (1–5)"
                name="risk-probability"
                type="number"
                min={1}
                max={5}
                value={form.probability}
                onChange={(event) =>
                  setForm({ ...form, probability: event.target.value })
                }
              />
            </div>
            <div>
              <Input
                label="Impact (1–5)"
                name="risk-impact"
                type="number"
                min={1}
                max={5}
                value={form.impact}
                onChange={(event) =>
                  setForm({ ...form, impact: event.target.value })
                }
              />
            </div>
          </div>
          <Select
            aria-label="Risk owner"
            label="Owner"
            value={form.owner_id}
            onChange={(event) =>
              setForm({ ...form, owner_id: event.target.value })
            }
            placeholder="Assign an owner"
            options={employees.map((e) => ({
              value: e.id,
              label: e.full_name,
            }))}
          />
          <div>
            <label className="label">Mitigation plan</label>
            <Textarea
              aria-label="Mitigation plan"
              value={form.mitigation}
              onChange={(event) =>
                setForm({ ...form, mitigation: event.target.value })
              }
              rows={3}
              placeholder="How will we reduce this risk?"
            />
          </div>
          <div>
            <Input
              label="Due by"
              name="risk-due"
              type="date"
              value={form.due_at}
              onChange={(event) =>
                setForm({ ...form, due_at: event.target.value })
              }
            />
          </div>
        </div>
      </Modal>

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title="Delete risk"
        description="This removes the risk from the register permanently."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Keep it
            </Button>
            <Button variant="danger" onClick={handleDelete} disabled={busy}>
              {busy ? "Deleting…" : "Delete risk"}
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink/70">
          Delete <span className="font-medium text-ink">{deleting?.title}</span>
          ? The audit trail still records this action.
        </p>
      </Modal>
    </div>
  );
}
