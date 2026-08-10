"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Plus, Trash2 } from "lucide-react";

import { createDecision, listEmployees, listGoals, listProjects } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { TagInput } from "@/components/knowledge/TagInput";
import type { EmployeeSummary, Goal, Project } from "@/types";
import { toastSuccess } from "@/components/ui/Toaster";

interface OptionDraft {
  title: string;
  description: string;
  pros: string;
  cons: string;
}

interface ParticipantDraft {
  employee_id: string;
  role: string;
}

interface FollowUpDraft {
  text: string;
  owner_id: string;
  project_id: string;
  goal_id: string;
  due_date: string;
}

const PARTICIPANT_ROLES = ["maker", "approver", "consulted", "informed"];
const STATUSES = ["proposed", "made", "implemented", "reviewed"];

export default function NewDecisionPage() {
  return (
    <Suspense fallback={null}>
      <NewDecisionContent />
    </Suspense>
  );
}

function NewDecisionContent() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [options, setOptions] = useState<OptionDraft[]>([
    { title: "", description: "", pros: "", cons: "" },
    { title: "", description: "", pros: "", cons: "" },
  ]);
  const [participants, setParticipants] = useState<ParticipantDraft[]>([]);
  const [followUps, setFollowUps] = useState<FollowUpDraft[]>([]);

  useEffect(() => {
    Promise.all([
      listEmployees({ page_size: 200 }).catch(() => [] as EmployeeSummary[]),
      listProjects({}).catch(() => [] as Project[]),
      listGoals({}).catch(() => [] as Goal[]),
    ]).then(([employeeList, projectList, goalList]) => {
      setEmployees(employeeList);
      setProjects(projectList);
      setGoals(goalList);
    });
  }, []);

  function updateOption(index: number, patch: Partial<OptionDraft>) {
    setOptions((prev) => prev.map((option, i) => (i === index ? { ...option, ...patch } : option)));
  }

  function updateParticipant(index: number, patch: Partial<ParticipantDraft>) {
    setParticipants((prev) => prev.map((participant, i) => (i === index ? { ...participant, ...patch } : participant)));
  }

  function updateFollowUp(index: number, patch: Partial<FollowUpDraft>) {
    setFollowUps((prev) => prev.map((action, i) => (i === index ? { ...action, ...patch } : action)));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setError("Title is required.");
      return;
    }
    const cleanOptions = options
      .map((option, i) => ({
        title: option.title.trim(),
        description: option.description.trim() || undefined,
        pros: option.pros.trim() || undefined,
        cons: option.cons.trim() || undefined,
        sort_order: i,
      }))
      .filter((option) => option.title.length > 0);
    const cleanParticipants = participants
      .filter((participant) => participant.employee_id)
      .map((participant) => ({
        employee_id: participant.employee_id,
        role: participant.role || "consulted",
      }));
    const cleanFollowUps = followUps
      .filter((action) => action.text.trim().length > 0)
      .map((action) => ({
        text: action.text.trim(),
        owner_id: action.owner_id || undefined,
        project_id: action.project_id || undefined,
        goal_id: action.goal_id || undefined,
        due_date: action.due_date || undefined,
        status: "pending",
      }));

    setSaving(true);
    try {
      let tags: string[] | undefined;
      const rawTags = form.get("tags");
      if (rawTags) {
        try {
          tags = JSON.parse(String(rawTags));
        } catch {
          tags = undefined;
        }
      }
      const decision = await createDecision({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        context: String(form.get("context") ?? "").trim() || undefined,
        impact: String(form.get("impact") ?? "").trim() || undefined,
        status: String(form.get("status") ?? "proposed") || "proposed",
        decision_maker_id: String(form.get("decision_maker_id") ?? "") || undefined,
        decision_date: String(form.get("decision_date") ?? "") || undefined,
        future_review_date: String(form.get("future_review_date") ?? "") || undefined,
        project_id: String(form.get("project_id") ?? "") || undefined,
        tags,
        options: cleanOptions.length > 0 ? cleanOptions : undefined,
        participants: cleanParticipants.length > 0 ? cleanParticipants : undefined,
        follow_up_actions: cleanFollowUps.length > 0 ? cleanFollowUps : undefined,
      });
      toastSuccess("Decision recorded");
      router.push(`/decisions/${decision.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create decision");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        breadcrumb="Decisions"
        title="New decision"
        description="Document the options, the trade-offs, and the choice."
      />
      <form onSubmit={handleSubmit} className="card space-y-4 p-6">
        {error && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{error}</div>}
        <Input label="Title" name="title" required placeholder="e.g. Choose the knowledge base platform" />
        <Textarea label="Description" name="description" rows={2} placeholder="One-line summary" />
        <Textarea label="Context" name="context" rows={3} placeholder="Background that led to this decision…" />
        <Textarea label="Expected impact" name="impact" rows={2} placeholder="What this decision changes…" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Status"
            name="status"
            defaultValue="proposed"
            options={STATUSES.map((s) => ({ value: s, label: s }))}
          />
          <Select
            label="Project"
            name="project_id"
            options={[{ value: "", label: "No project" }, ...projects.map((p) => ({ value: p.id, label: p.name }))]}
          />
          <Select
            label="Decision maker"
            name="decision_maker_id"
            options={[{ value: "", label: "Unassigned" }, ...employees.map((e) => ({ value: e.id, label: e.full_name }))]}
          />
          <Input label="Decision date" name="decision_date" type="date" />
          <Input label="Future review date" name="future_review_date" type="date" />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-ink">Tags</label>
          <TagInput name="tags" />
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[13px] font-medium text-ink">Options</label>
            <Button type="button" size="sm" variant="ghost" onClick={() => setOptions((prev) => [...prev, { title: "", description: "", pros: "", cons: "" }])}>
              <Plus className="h-4 w-4" /> Add option
            </Button>
          </div>
          <div className="space-y-2">
            {options.map((option, index) => (
              <div key={index} className="rounded-lg border border-line bg-canvas p-3">
                <div className="flex items-center gap-2">
                  <span className="w-6 shrink-0 text-[12px] font-bold text-faint">{index + 1}.</span>
                  <Input
                    placeholder="Option title"
                    value={option.title}
                    onChange={(e) => updateOption(index, { title: e.target.value })}
                    className="text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setOptions((prev) => prev.filter((_, i) => i !== index))}
                    className="shrink-0 p-1 text-faint hover:text-danger"
                    aria-label="Remove option"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-2 space-y-2">
                  <Input
                    placeholder="Short description (optional)"
                    value={option.description}
                    onChange={(e) => updateOption(index, { description: e.target.value })}
                    className="text-sm"
                  />
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Textarea
                      placeholder="Pros"
                      rows={2}
                      value={option.pros}
                      onChange={(e) => updateOption(index, { pros: e.target.value })}
                      className="text-sm"
                    />
                    <Textarea
                      placeholder="Cons"
                      rows={2}
                      value={option.cons}
                      onChange={(e) => updateOption(index, { cons: e.target.value })}
                      className="text-sm"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[13px] font-medium text-ink">Participants</label>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setParticipants((prev) => [...prev, { employee_id: "", role: "consulted" }])}
            >
              <Plus className="h-4 w-4" /> Add participant
            </Button>
          </div>
          {participants.length === 0 ? (
            <p className="text-[12px] text-faint">No participants added yet.</p>
          ) : (
            <div className="space-y-2">
              {participants.map((participant, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Select
                    value={participant.employee_id}
                    onChange={(e) => updateParticipant(index, { employee_id: e.target.value })}
                    placeholder="Select employee"
                    options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
                    className="flex-1"
                  />
                  <Select
                    value={participant.role}
                    onChange={(e) => updateParticipant(index, { role: e.target.value })}
                    options={PARTICIPANT_ROLES.map((r) => ({ value: r, label: r }))}
                    className="w-36"
                  />
                  <button
                    type="button"
                    onClick={() => setParticipants((prev) => prev.filter((_, i) => i !== index))}
                    className="shrink-0 p-1 text-faint hover:text-danger"
                    aria-label="Remove participant"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-[13px] font-medium text-ink">Follow-up actions</label>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setFollowUps((prev) => [...prev, { text: "", owner_id: "", project_id: "", goal_id: "", due_date: "" }])}
            >
              <Plus className="h-4 w-4" /> Add action
            </Button>
          </div>
          <p className="mb-2 text-[12px] text-faint">Each action becomes a real task when executed — with an owner, goal, project and due date.</p>
          {followUps.length === 0 ? (
            <p className="rounded-lg border border-dashed border-line px-3 py-3 text-[12px] text-faint">
              No follow-up actions yet. Add the concrete next steps this decision requires.
            </p>
          ) : (
            <div className="space-y-2">
              {followUps.map((action, index) => (
                <div key={index} className="rounded-lg border border-line bg-canvas p-3">
                  <div className="flex items-center gap-2">
                    <span className="w-6 shrink-0 text-[12px] font-bold text-faint">{index + 1}.</span>
                    <Input
                      placeholder="Action text (e.g. Build the onboarding flow)"
                      value={action.text}
                      onChange={(e) => updateFollowUp(index, { text: e.target.value })}
                      className="text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setFollowUps((prev) => prev.filter((_, i) => i !== index))}
                      className="shrink-0 p-1 text-faint hover:text-danger"
                      aria-label="Remove action"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <Select
                      value={action.owner_id}
                      onChange={(e) => updateFollowUp(index, { owner_id: e.target.value })}
                      placeholder="Owner"
                      options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
                      className="text-sm"
                    />
                    <Select
                      value={action.project_id}
                      onChange={(e) => updateFollowUp(index, { project_id: e.target.value })}
                      placeholder="Project"
                      options={[{ value: "", label: "No project" }, ...projects.map((p) => ({ value: p.id, label: p.name }))]}
                      className="text-sm"
                    />
                    <Select
                      value={action.goal_id}
                      onChange={(e) => updateFollowUp(index, { goal_id: e.target.value })}
                      placeholder="Goal"
                      options={[{ value: "", label: "No goal" }, ...goals.map((g) => ({ value: g.id, label: g.name }))]}
                      className="text-sm"
                    />
                    <Input
                      type="date"
                      value={action.due_date}
                      onChange={(e) => updateFollowUp(index, { due_date: e.target.value })}
                      placeholder="Due date"
                      className="text-sm"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Link href="/decisions"><Button type="button" variant="ghost">Cancel</Button></Link>
          <Button type="submit" loading={saving}>Record decision</Button>
        </div>
      </form>
    </div>
  );
}
