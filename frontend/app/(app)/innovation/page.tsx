"use client";

import { Suspense, useEffect, useState } from "react";
import { ArrowBigUp, Lightbulb, Plus, Rocket } from "lucide-react";

import {
  createIdea,
  getInnovationStats,
  listIdeas,
  promoteIdea,
  setIdeaStatus,
  voteIdea,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Idea } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo, titleCase } from "@/lib/utils";

const STATUSES = ["submitted", "in_discussion", "voting", "in_review", "approved", "in_progress", "implemented", "rejected"];

export default function InnovationPage() {
  return (
    <Suspense fallback={null}>
      <InnovationContent />
    </Suspense>
  );
}

function InnovationContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.COMMUNICATION_MANAGE);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [stats, setStats] = useState<{ total: number; by_status: { status: string; count: number }[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, statsData] = await Promise.all([
        listIdeas({ status: status || undefined, search: search || undefined, limit: 200 }),
        getInnovationStats(),
      ]);
      setIdeas(list);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load ideas");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function upvote(idea: Idea) {
    try {
      const result = await voteIdea(idea.id);
      setIdeas((prev) => prev.map((i) => (i.id === idea.id ? { ...i, voted: result.voted, vote_count: result.vote_count } : i)));
    } catch {
      /* ignore */
    }
  }

  async function changeStatus(idea: Idea, newStatus: string) {
    try {
      const updated = await setIdeaStatus(idea.id, newStatus);
      setIdeas((prev) => prev.map((i) => (i.id === idea.id ? updated : i)));
    } catch {
      /* ignore */
    }
  }

  async function promote(idea: Idea) {
    try {
      const updated = await promoteIdea(idea.id);
      setIdeas((prev) => prev.map((i) => (i.id === idea.id ? updated : i)));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Innovation Hub"
        description="Share ideas and shape what your organization builds next."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New idea
          </Button>
        }
      />

      {stats && (
        <div className="flex flex-wrap gap-2">
          <Badge tone="brand">{stats.total} ideas</Badge>
          {stats.by_status.slice(0, 4).map((s) => (
            <Badge key={s.status} tone="neutral">{titleCase(s.status)}: {s.count}</Badge>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search ideas…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="All statuses"
          options={STATUSES.map((s) => ({ value: s, label: titleCase(s) }))}
          className="w-44"
        />
        <Button variant="secondary" size="sm" onClick={load}>Search</Button>
      </div>

      {error ? (
        <ErrorState title="Could not load ideas" message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading ideas" /></div>
      ) : ideas.length === 0 ? (
        <EmptyState
          icon={Lightbulb}
          title="No ideas yet"
          description="Share your first idea with the organization."
          action={<Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> New idea</Button>}
        />
      ) : (
        <div className="space-y-2">
          {ideas.map((idea) => (
            <div key={idea.id} className="rounded-lg border border-line bg-surface p-4">
              <div className="flex items-start gap-4">
                <div className="flex w-12 shrink-0 flex-col items-center rounded-md bg-brand-soft/50 py-2">
                  <ArrowBigUp className={`h-4 w-4 ${idea.voted ? "fill-brand text-brand" : "text-brand"}`} />
                  <span className="text-sm font-bold text-brand">{idea.vote_count}</span>
                  <Button variant="ghost" size="sm" className="-m-1 p-1" onClick={() => upvote(idea)}>
                    {idea.voted ? "Voted" : "Vote"}
                  </Button>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[15px] font-semibold text-ink">{idea.title}</p>
                    <Badge tone="brand">{titleCase(idea.status)}</Badge>
                    {idea.project_name && <Badge tone="success"><Rocket className="h-3 w-3" /> {idea.project_name}</Badge>}
                  </div>
                  {idea.description && <p className="mt-1 line-clamp-2 text-[13px] text-muted">{idea.description}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-faint">
                    <span className="flex items-center gap-1.5"><Avatar name={idea.author_name} size="xs" /> {idea.author_name}</span>
                    <span>· {timeAgo(idea.created_at)}</span>
                    {idea.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="rounded bg-surface-muted px-1.5 py-0.5 text-[11px]">#{tag}</span>
                    ))}
                    {idea.ai_insight && <span className="text-brand">✨ AI insight available</span>}
                  </div>
                  {canManage && (
                    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
                      <Select
                        value={idea.status}
                        onChange={(e) => changeStatus(idea, e.target.value)}
                        options={STATUSES.map((s) => ({ value: s, label: titleCase(s) }))}
                        className="w-40"
                      />
                      {!idea.project_id && (
                        <Button variant="secondary" size="sm" onClick={() => promote(idea)}>
                          <Rocket className="h-4 w-4" /> Promote to project
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateIdeaModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={async (payload) => {
          await createIdea(payload);
          setCreateOpen(false);
          load();
        }}
      />
    </div>
  );
}

function CreateIdeaModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (payload: {
    title: string;
    description?: string;
    problem?: string;
    solution?: string;
    impact?: string;
    tags?: string[];
  }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [problem, setProblem] = useState("");
  const [solution, setSolution] = useState("");
  const [impact, setImpact] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setError(null);
    try {
      await onCreated({
        title: title.trim(),
        description: description.trim() || undefined,
        problem: problem.trim() || undefined,
        solution: solution.trim() || undefined,
        impact: impact.trim() || undefined,
        tags: tags.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean),
      });
      setTitle("");
      setDescription("");
      setProblem("");
      setSolution("");
      setImpact("");
      setTags("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create idea");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New idea"
      description="Share an idea worth exploring."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Submit idea</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Title" placeholder="e.g. Automate weekly reports" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea label="Description" placeholder="What is the idea about?" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        <Textarea label="Problem" placeholder="What problem does it solve?" value={problem} onChange={(e) => setProblem(e.target.value)} rows={2} />
        <Textarea label="Solution" placeholder="How would it work?" value={solution} onChange={(e) => setSolution(e.target.value)} rows={2} />
        <Textarea label="Impact" placeholder="What impact would it have?" value={impact} onChange={(e) => setImpact(e.target.value)} rows={2} />
        <Input label="Tags (comma-separated)" placeholder="automation, reports" value={tags} onChange={(e) => setTags(e.target.value)} />
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
