"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, GraduationCap, Users } from "lucide-react";

import { getAcademy, joinAcademy, leaveAcademy } from "@/lib/api";
import type { Academy } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

export default function AcademyDetailPage() {
  return (
    <Suspense fallback={null}>
      <AcademyDetail />
    </Suspense>
  );
}

function AcademyDetail() {
  const { id } = useParams<{ id: string }>();
  const [academy, setAcademy] = useState<Academy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAcademy(await getAcademy(id));
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

  if (loading) return <Spinner label="Loading academy" />;
  if (error && !academy) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }
  if (!academy) return null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href="/learning?tab=academies"
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
        title={academy.name}
        description={academy.description ?? "No description"}
        breadcrumb="Academy"
        actions={
          academy.joined ? (
            <Button
              variant="secondary"
              loading={busy}
              onClick={() =>
                run(async () => {
                  await leaveAcademy(academy.id);
                }, "Left academy")
              }
            >
              Leave academy
            </Button>
          ) : (
            <Button
              loading={busy}
              onClick={() =>
                run(async () => {
                  await joinAcademy(academy.id);
                }, "Joined academy")
              }
            >
              Join academy
            </Button>
          )
        }
      />

      <div className="mb-5 flex flex-wrap gap-2">
        <Badge tone="brand">{academy.category ?? "General"}</Badge>
        <Badge tone={statusTone(academy.status ?? "published")}>
          {academy.status ?? "published"}
        </Badge>
        <Badge tone="neutral">
          <Users className="h-3 w-3" /> {academy.member_count ?? 0} members
        </Badge>
        <Badge tone="neutral">
          <GraduationCap className="h-3 w-3" /> {academy.course_count ?? 0}{" "}
          courses
        </Badge>
      </div>

      {academy.cover_url && (
        <img
          src={academy.cover_url}
          alt={academy.name}
          className="mb-6 h-40 w-full rounded-xl object-cover"
        />
      )}

      <Card title="Curriculum" subtitle="Focus areas of this academy">
        {!academy.curriculum?.length ? (
          <EmptyState
            title="No curriculum"
            description="This academy has no curriculum areas defined yet."
          />
        ) : (
          <div className="flex flex-wrap gap-2">
            {academy.curriculum.map((c) => (
              <Badge key={c} tone="brand">
                {c}
              </Badge>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
