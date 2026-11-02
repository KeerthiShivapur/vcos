"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Plus, Target, Trash2 } from "lucide-react";

import {
  addKeyResult,
  deleteKeyResult,
  getGoal,
  listKeyResults,
  updateKeyResult,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Goal, KeyResult } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function GoalDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailContent />
    </Suspense>
  );
}

function DetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.GOALS_MANAGE);

  const [goal, setGoal] = useState<Goal | null>(null);
  const [keyResults, setKeyResults] = useState<KeyResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [goalData, krList] = await Promise.all([
        getGoal(id),
        listKeyResults(id),
      ]);
      setGoal(goalData);
      setKeyResults(krList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load goal");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleAddKr(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) return;
    setSaving(true);
    setFormError(null);
    try {
      await addKeyResult(id, {
        title,
        target: form.get("target") ? Number(form.get("target")) : undefined,
        unit: String(form.get("unit") ?? "").trim() || undefined,
        metric: String(form.get("metric") ?? "").trim() || undefined,
        current: form.get("current") ? Number(form.get("current")) : 0,
      });
      toastSuccess("Key result added");
      setShowAdd(false);
      await load();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Unable to add key result",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdateKr(kr: KeyResult, current: number) {
    try {
      const updated = await updateKeyResult(id, kr.id, { current });
      setKeyResults((list) => list.map((k) => (k.id === kr.id ? updated : k)));
      toastSuccess("Key result updated");
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "Unable to update key result",
      );
    }
  }

  async function handleDeleteKr(kr: KeyResult) {
    try {
      await deleteKeyResult(id, kr.id);
      toastSuccess("Key result deleted");
      await load();
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "Unable to delete key result",
      );
    }
  }

  if (error) return <ErrorState title="Could not load goal" message={error} />;
  if (loading || !goal)
    return (
      <div className="flex justify-center py-24">
        <Spinner label="Loading goal" />
      </div>
    );

  const achieved = keyResults.filter(
    (kr) => kr.target && kr.current !== null && kr.current >= kr.target,
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Goals"
        title={goal.name}
        description={`${goal.scope} goal · ${goal.owner_name ?? "no owner"} · ${formatDate(goal.end_date)}`}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={statusTone(goal.status)}>{goal.status}</Badge>
            <Badge
              tone={
                goal.priority === "critical"
                  ? "danger"
                  : goal.priority === "high"
                    ? "warning"
                    : "neutral"
              }
            >
              {goal.priority}
            </Badge>
          </div>
        }
      />

      <Card title="Progress" subtitle={`${Math.round(goal.progress)}% overall`}>
        <div className="h-2 overflow-hidden rounded-full bg-canvas">
          <div
            className="h-full rounded-full bg-brand"
            style={{ width: `${Math.round(goal.progress)}%` }}
          />
        </div>
        <p className="mt-3 text-[13px] text-muted">
          {achieved} of {keyResults.length} key results achieved ·{" "}
          {goal.description ?? "No description"}
        </p>
      </Card>

      <Card
        title="Key results"
        subtitle="Measurable outcomes"
        actions={
          canManage ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setShowAdd(true)}
            >
              <Plus className="h-3.5 w-3.5" /> Add KR
            </Button>
          ) : undefined
        }
      >
        {keyResults.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No key results"
            description="Add measurable outcomes to track progress."
          />
        ) : (
          <ul className="space-y-4">
            {keyResults.map((kr) => {
              const pct =
                kr.target && kr.current !== null
                  ? Math.min(100, Math.round((kr.current / kr.target) * 100))
                  : 0;
              return (
                <li key={kr.id} className="rounded-lg border border-line p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-ink">
                        {kr.title}
                      </p>
                      <p className="text-[12px] text-faint">
                        {kr.metric ?? "progress"} · {kr.current ?? 0}
                        {kr.unit ? ` ${kr.unit}` : ""} of {kr.target ?? 0}
                        {kr.unit ? ` ${kr.unit}` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        tone={
                          pct >= 100
                            ? "success"
                            : kr.status === "at_risk"
                              ? "danger"
                              : "brand"
                        }
                      >
                        {pct}%
                      </Badge>
                      {canManage && (
                        <button
                          onClick={() => handleDeleteKr(kr)}
                          className="rounded-lg p-1 text-faint hover:bg-danger/10 hover:text-danger"
                          title="Delete key result"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-canvas">
                    <div
                      className="h-full rounded-full bg-brand"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  {canManage && (
                    <div className="mt-3 flex items-center gap-2">
                      <Input
                        type="number"
                        min={0}
                        step="any"
                        defaultValue={kr.current ?? 0}
                        aria-label="Current value"
                        className="h-8 w-32"
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            handleUpdateKr(
                              kr,
                              Number((event.target as HTMLInputElement).value),
                            );
                          }
                        }}
                        onBlur={(event) => {
                          const value = Number(event.target.value);
                          if (value !== kr.current) handleUpdateKr(kr, value);
                        }}
                      />
                      <span className="text-[12px] text-faint">
                        Enter to update current value
                      </span>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Modal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title="Add key result"
        description="A measurable outcome for this goal."
      >
        <form onSubmit={handleAddKr} className="space-y-4">
          {formError && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
              {formError}
            </div>
          )}
          <Input
            label="Title"
            name="title"
            required
            placeholder="Increase retention to 60%"
          />
          <div className="grid gap-4 sm:grid-cols-3">
            <Input
              label="Target"
              name="target"
              type="number"
              min={0}
              step="any"
            />
            <Input
              label="Current"
              name="current"
              type="number"
              min={0}
              step="any"
              defaultValue="0"
            />
            <Input label="Unit" name="unit" placeholder="%" />
          </div>
          <Input label="Metric" name="metric" placeholder="retention" />
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowAdd(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Add key result
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
