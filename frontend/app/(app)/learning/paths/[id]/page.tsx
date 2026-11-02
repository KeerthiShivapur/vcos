"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, Flag, MapPin, Target } from "lucide-react";

import {
  completePathStep,
  enrollLearningPath,
  getCareerPath,
  getLearningPath,
  myLearningPathEnrollments,
} from "@/lib/api";
import type {
  CareerPath,
  LearningPath,
  LearningPathEnrollment,
} from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

export default function PathDetailPage() {
  return (
    <Suspense fallback={null}>
      <PathDetail />
    </Suspense>
  );
}

function PathDetail() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const isCareer = searchParams.get("career") === "1";

  const [path, setPath] = useState<LearningPath | null>(null);
  const [career, setCareer] = useState<CareerPath | null>(null);
  const [enrollment, setEnrollment] = useState<LearningPathEnrollment | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (isCareer) {
        const [p, enrollments] = await Promise.all([
          getCareerPath(id),
          myLearningPathEnrollments(),
        ]);
        setCareer(p);
        setEnrollment(enrollments.find((e) => e.path_id === id) ?? null);
      } else {
        const [p, enrollments] = await Promise.all([
          getLearningPath(id),
          myLearningPathEnrollments(),
        ]);
        setPath(p);
        setEnrollment(enrollments.find((e) => e.path_id === id) ?? null);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id, isCareer]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const t = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(t);
  }, [notice]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(ok);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Spinner label="Loading path" />;
  if (error && !path && !career) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }

  const backHref = isCareer ? "/learning?tab=career" : "/learning?tab=paths";

  if (isCareer && career) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <Link
          href={backHref}
          className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-faint transition-colors hover:text-brand"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Learning Center
        </Link>
        {error && (
          <div className="mb-4 rounded-lg border border-danger/20 bg-danger/5 px-4 py-2.5 text-[13px] text-danger">
            {error}
          </div>
        )}
        {notice && (
          <div className="mb-4 rounded-lg border border-success/20 bg-success/5 px-4 py-2.5 text-[13px] text-success">
            {notice}
          </div>
        )}
        <PageHeader
          title={career.title}
          description={career.description ?? "No description"}
          breadcrumb="Career Path"
        />
        <div className="mb-5 flex flex-wrap gap-2">
          <Badge tone="brand">
            <Target className="h-3 w-3" /> Career
          </Badge>
          {career.department && (
            <Badge tone="neutral">{career.department}</Badge>
          )}
          <Badge tone="neutral">{career.levels.length} levels</Badge>
        </div>
        <Card title="Levels" subtitle="Progression stages on this path">
          <div className="space-y-3">
            {career.levels.map((level, i) => (
              <div
                key={level}
                className="flex items-center gap-3 rounded-xl border border-line p-3.5"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-[11px] font-bold text-brand">
                  {i + 1}
                </div>
                <div>
                  <p className="text-[13px] font-medium text-ink">{level}</p>
                  {career.steps?.[i]?.required_skills.length ? (
                    <p className="mt-0.5 text-[11px] text-faint">
                      Requires:{" "}
                      {career.steps[i].required_skills
                        .map((s) => s.name ?? s.skill ?? "")
                        .join(", ")}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    );
  }

  if (!path) return null;
  const doneSteps = new Set(enrollment?.completed_step_ids ?? []);
  const steps = path.steps ?? [];

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href={backHref}
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-faint transition-colors hover:text-brand"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Learning Center
      </Link>
      {error && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger/5 px-4 py-2.5 text-[13px] text-danger">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 rounded-lg border border-success/20 bg-success/5 px-4 py-2.5 text-[13px] text-success">
          {notice}
        </div>
      )}

      <PageHeader
        title={path.title}
        description={path.description ?? "No description"}
        breadcrumb="Learning Path"
        actions={
          enrollment ? (
            <div className="flex items-center gap-3">
              <Badge tone={statusTone(enrollment.status)}>
                {enrollment.status}
              </Badge>
              <span className="text-sm font-semibold text-ink">
                {enrollment.progress}%
              </span>
            </div>
          ) : (
            <Button
              loading={busy}
              onClick={() =>
                run(async () => {
                  await enrollLearningPath(path.id);
                }, "Enrolled in path")
              }
            >
              Start Path
            </Button>
          )
        }
      />

      <div className="mb-5 flex flex-wrap gap-2">
        <Badge tone="brand">{path.category ?? "General"}</Badge>
        <Badge tone="neutral">{path.difficulty ?? "Any level"}</Badge>
        <Badge tone="neutral">
          <Flag className="h-3 w-3" /> Target: {path.target_role ?? "—"}
        </Badge>
        <Badge tone="neutral">
          <MapPin className="h-3 w-3" /> ~{path.estimated_days ?? 0} days
        </Badge>
      </div>

      <div className="mb-5 flex flex-wrap gap-1.5">
        {path.tags.map((t) => (
          <Badge key={t} tone="neutral">
            {t}
          </Badge>
        ))}
      </div>

      {enrollment && (
        <Card title="My Progress" className="mb-6">
          <div className="h-2 overflow-hidden rounded-full bg-surface">
            <div
              className="h-full rounded-full bg-brand"
              style={{ width: `${enrollment.progress}%` }}
            />
          </div>
          <p className="mt-2 text-[11px] text-faint">
            {doneSteps.size} of {steps.length} steps completed
          </p>
        </Card>
      )}

      <Card title="Path Steps" subtitle="Complete each step to finish the path">
        {steps.length === 0 ? (
          <EmptyState
            title="No steps yet"
            description="This path has no steps defined yet."
          />
        ) : (
          <div className="space-y-2.5">
            {steps.map((s) => {
              const done = doneSteps.has(s.id);
              return (
                <div
                  key={s.id}
                  className={`flex items-start justify-between gap-3 rounded-xl border p-3.5 ${done ? "border-success/30 bg-success/5" : "border-line"}`}
                >
                  <div className="flex items-start gap-3">
                    {done ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                    ) : (
                      <div className="mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 border-line" />
                    )}
                    <div>
                      <p className="text-[13px] font-medium text-ink">
                        {s.position}. {s.title}
                      </p>
                      {s.description && (
                        <p className="mt-0.5 text-xs text-faint">
                          {s.description}
                        </p>
                      )}
                    </div>
                  </div>
                  {!done && enrollment && (
                    <Button
                      size="sm"
                      loading={busy}
                      onClick={() =>
                        run(async () => {
                          await completePathStep(enrollment.id, s.id);
                        }, "Step completed")
                      }
                    >
                      Complete
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
