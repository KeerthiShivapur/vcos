"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, BookOpen, Clock, ExternalLink, FileQuestion, ListOrdered, Play } from "lucide-react";

import {
  completeCourse,
  completeCourseLesson,
  enrollCourse,
  getCourse,
  myCourseEnrollments,
} from "@/lib/api";
import type { Course, CourseEnrollment } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

export default function CourseDetailPage() {
  return (
    <Suspense fallback={null}>
      <CourseDetail />
    </Suspense>
  );
}

function CourseDetail() {
  const { id } = useParams<{ id: string }>();
  const [course, setCourse] = useState<Course | null>(null);
  const [enrollment, setEnrollment] = useState<CourseEnrollment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [detail, enrollments] = await Promise.all([getCourse(id), myCourseEnrollments()]);
      setCourse(detail);
      setEnrollment(enrollments.find((e) => e.course_id === id) ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

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

  if (loading) return <Spinner label="Loading course" />;
  if (error && !course) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }
  if (!course) return null;

  const byModule = (lessonId: string | null | undefined) => lessonId ?? "";

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <Link href="/learning?tab=courses" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-faint transition-colors hover:text-brand">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Learning Center
      </Link>

      {error && <div className="mb-4 rounded-lg border border-danger/20 bg-danger/5 px-4 py-2.5 text-[13px] text-danger">{error}</div>}
      {notice && <div className="mb-4 rounded-lg border border-success/20 bg-success/5 px-4 py-2.5 text-[13px] text-success">{notice}</div>}

      <PageHeader
        title={course.title}
        description={course.description ?? "No description"}
        breadcrumb="Course"
        actions={
          enrollment ? (
            <div className="flex items-center gap-3">
              <Badge tone={statusTone(enrollment.status)}>{enrollment.status}</Badge>
              <span className="text-sm font-semibold text-ink">{enrollment.progress}%</span>
            </div>
          ) : (
            <Button loading={busy} onClick={() => run(async () => { await enrollCourse(course.id); }, "Enrolled in course")}>Enroll in course</Button>
          )
        }
      />

      <div className="mb-5 flex flex-wrap gap-2">
        <Badge tone="brand">{course.category ?? "General"}</Badge>
        <Badge tone="neutral">{course.difficulty ?? "Any level"}</Badge>
        <Badge tone="neutral"><Clock className="h-3 w-3" /> {course.duration_minutes ?? 0} min</Badge>
        <Badge tone="neutral"><FileQuestion className="h-3 w-3" /> {course.quizzes?.length ?? 0} quizzes</Badge>
        {course.format && <Badge tone="neutral">{course.format}</Badge>}
      </div>

      <div className="mb-5 flex flex-wrap gap-1.5">
        {course.skills.map((s) => <Badge key={s} tone="brand">{s}</Badge>)}
        {course.tags.map((t) => <Badge key={t} tone="neutral">{t}</Badge>)}
      </div>

      {course.external_url && (
        <a href={course.external_url} target="_blank" rel="noreferrer" className="btn-secondary mb-5 inline-flex items-center gap-1.5">
          <ExternalLink className="h-3.5 w-3.5" /> Open external course
        </a>
      )}

      {enrollment && (
        <Card title="My Progress" className="mb-6">
          <div className="h-2 overflow-hidden rounded-full bg-surface">
            <div className="h-full rounded-full bg-brand" style={{ width: `${enrollment.progress}%` }} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {enrollment.status !== "completed" && (
              <Button size="sm" loading={busy} onClick={() => run(async () => { await completeCourse(enrollment.id); }, "Course completed")}>
                Complete course
              </Button>
            )}
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Curriculum" subtitle="Modules and lessons">
            {course.modules?.length === 0 && course.lessons?.length === 0 ? (
              <EmptyState title="No content yet" description="This course has no modules or lessons yet." />
            ) : (
              <div className="space-y-5">
                {course.modules?.map((m) => (
                  <div key={m.id}>
                    <div className="flex items-center gap-2">
                      <ListOrdered className="h-4 w-4 text-brand" />
                      <p className="text-sm font-semibold text-ink">{m.position}. {m.title}</p>
                    </div>
                    {m.description && <p className="mt-1 text-xs text-faint">{m.description}</p>}
                    <div className="mt-2 space-y-2">
                      {course.lessons
                        ?.filter((l) => byModule(l.module_id) === m.id)
                        .map((l) => (
                          <div key={l.id} className="flex items-center justify-between gap-3 rounded-lg border border-line px-3.5 py-2.5">
                            <div className="flex items-center gap-2.5">
                              <Play className="h-3.5 w-3.5 text-faint" />
                              <span className="text-[13px] text-ink">{l.title}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              {l.duration_minutes ? <span className="text-[11px] text-faint">{l.duration_minutes} min</span> : null}
                              {enrollment && (
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  loading={busy}
                                  onClick={() => run(async () => { await completeCourseLesson(enrollment.id, l.id); }, "Lesson marked complete")}
                                >
                                  Mark done
                                </Button>
                              )}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                ))}
                {course.lessons?.some((l) => !l.module_id) && (
                  <div className="mt-2 space-y-2">
                    {course.lessons.filter((l) => !l.module_id).map((l) => (
                      <div key={l.id} className="flex items-center justify-between gap-3 rounded-lg border border-line px-3.5 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <Play className="h-3.5 w-3.5 text-faint" />
                          <span className="text-[13px] text-ink">{l.title}</span>
                        </div>
                        {enrollment && (
                          <Button size="sm" variant="secondary" loading={busy} onClick={() => run(async () => { await completeCourseLesson(enrollment.id, l.id); }, "Lesson marked complete")}>
                            Mark done
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>

        <div>
          <Card title="Quizzes" subtitle="Knowledge checks">
            {course.quizzes?.length === 0 ? (
              <p className="text-[13px] text-faint">No quizzes attached.</p>
            ) : (
              <div className="space-y-2.5">
                {course.quizzes?.map((q) => (
                  <div key={q.id} className="rounded-lg border border-line p-3.5">
                    <p className="text-[13px] font-medium text-ink">{q.title}</p>
                    <p className="mt-1 text-[11px] text-faint">{q.question_count} questions · pass at {q.passing_score}%</p>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {course.certificate_title && (
            <Card title="Certificate" className="mt-6">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <BookOpen className="h-5 w-5" />
                </div>
                <p className="text-[13px] text-ink">Earn: <b>{course.certificate_title}</b></p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
