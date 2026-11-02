"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CalendarClock, Play, Plus, Radio, Search, Users } from "lucide-react";

import {
  createMeeting,
  getMeetingAnalyticsOverview,
  getMeetingSuggestions,
  getMyEmployee,
  joinMeeting,
  listEmployees,
  listMeetings,
  listProjects,
  listUpcomingMeetings,
  meetingByCode,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type {
  Employee,
  EmployeeSummary,
  Meeting,
  MeetingAnalyticsOverview,
  MeetingSuggestionsResponse,
  MeetingWithSession,
  Project,
} from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { toastSuccess, toastError } from "@/components/ui/Toaster";

function IntelCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="card p-4">
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
        {label}
      </p>
      <p className="mt-1 text-[20px] font-semibold text-ink">{value}</p>
      <p className="text-[12px] text-muted">{detail}</p>
    </div>
  );
}

export default function MeetingsPage() {
  return (
    <Suspense fallback={null}>
      <MeetingsContent />
    </Suspense>
  );
}

const MEETING_TYPES = [
  "team",
  "standup",
  "one_on_one",
  "review",
  "planning",
  "retrospective",
  "client",
  "interview",
  "board",
  "other",
];
const SCOPES = ["organization", "department", "personal"];

function MeetingsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.MEETINGS_MANAGE);

  const [upcoming, setUpcoming] = useState<MeetingWithSession[]>([]);
  const [completed, setCompleted] = useState<Meeting[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [myEmployee, setMyEmployee] = useState<Employee | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState("personal");

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [attendeeIds, setAttendeeIds] = useState<string[]>([]);

  const [joinCode, setJoinCode] = useState("");
  const [joining, setJoining] = useState(false);

  const [analytics, setAnalytics] = useState<MeetingAnalyticsOverview | null>(
    null,
  );
  const [suggestions, setSuggestions] =
    useState<MeetingSuggestionsResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        up,
        done,
        empList,
        projectList,
        me,
        analyticsData,
        suggestionData,
      ] = await Promise.all([
        listUpcomingMeetings({ scope }),
        listMeetings({ status: "completed" }).catch(() => [] as Meeting[]),
        listEmployees({ page_size: 200 }),
        listProjects().catch(() => [] as Project[]),
        getMyEmployee().catch(() => null),
        getMeetingAnalyticsOverview(30).catch(() => null),
        getMeetingSuggestions({ duration_minutes: 30, days: 5 }).catch(
          () => null,
        ),
      ]);
      setUpcoming(up);
      setCompleted(done);
      setEmployees(empList);
      setProjects(projectList);
      setMyEmployee(me);
      setAnalytics(analyticsData);
      setSuggestions(suggestionData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load meetings");
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFormError(null);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setFormError("Meeting title is required.");
      return;
    }
    const startAt = String(form.get("start_at") ?? "");
    const endAt = String(form.get("end_at") ?? "");
    setSaving(true);
    try {
      await createMeeting({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        meeting_type: String(form.get("meeting_type") ?? "team"),
        project_id: String(form.get("project_id") ?? "") || undefined,
        organizer_id: myEmployee?.id ?? undefined,
        start_at: startAt ? new Date(startAt).toISOString() : undefined,
        end_at: endAt ? new Date(endAt).toISOString() : undefined,
        location: String(form.get("location") ?? "").trim() || undefined,
        meeting_link:
          String(form.get("meeting_link") ?? "").trim() || undefined,
        attendee_ids: attendeeIds.length ? attendeeIds : undefined,
      });
      toastSuccess("Meeting scheduled");
      setShowCreate(false);
      setAttendeeIds([]);
      await load();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Unable to schedule meeting",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleJoinNow(meeting: MeetingWithSession) {
    try {
      const result = await joinMeeting(meeting.id, "desktop");
      toastSuccess(`You joined "${meeting.title}"`);
      window.location.href = `/meetings/${meeting.id}?joined=1&session=${result.session.id}`;
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to join meeting");
    }
  }

  async function handleJoinByCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = joinCode.trim();
    if (!code) return;
    setJoining(true);
    try {
      const meeting = await meetingByCode(code);
      await joinMeeting(meeting.id, "desktop");
      toastSuccess(`Joining "${meeting.title}"`);
      window.location.href = `/meetings/${meeting.id}?joined=1`;
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "No meeting found for that code",
      );
    } finally {
      setJoining(false);
    }
  }

  function toggleAttendee(employeeId: string) {
    setAttendeeIds((ids) =>
      ids.includes(employeeId)
        ? ids.filter((id) => id !== employeeId)
        : [...ids, employeeId],
    );
  }

  const live = upcoming.filter(
    (m) => m.status === "active" || m.session?.status === "live",
  );
  const scheduled = upcoming.filter((m) => m.status === "scheduled");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Meetings"
        description="Virtual office hub — join live sessions, review upcoming meetings and revisit past ones."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> Schedule meeting
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={handleJoinByCode} className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
            <Input
              className="h-9 w-44 pl-8"
              placeholder="Join with code (e.g. KYZ3YV9L)"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            />
          </div>
          <Button size="sm" variant="secondary" type="submit" loading={joining}>
            <Play className="h-3.5 w-3.5" /> Join
          </Button>
        </form>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[12px] font-medium text-faint">Show:</span>
          <Select
            className="h-9 w-40"
            aria-label="Scope"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            options={SCOPES.map((s) => ({ value: s, label: s }))}
          />
        </div>
      </div>

      {error ? (
        <ErrorState title="Could not load meetings" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading meetings" />
        </div>
      ) : upcoming.length === 0 && completed.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="No meetings"
          description="Schedule your first meeting to get started."
          action={
            canManage ? (
              <Button size="sm" onClick={() => setShowCreate(true)}>
                <Plus className="h-4 w-4" /> Schedule meeting
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-8">
          {(analytics || suggestions) && (
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {analytics && (
                <>
                  <IntelCard
                    label="Meetings (30d)"
                    value={String(analytics.meetings_total)}
                    detail={`${analytics.meetings_completed} completed`}
                  />
                  <IntelCard
                    label="Time in meetings"
                    value={`${analytics.time_in_meetings_hours}h`}
                    detail={`avg ${analytics.avg_duration_minutes}m`}
                  />
                  <IntelCard
                    label="Action completion"
                    value={`${analytics.action_completion_rate}%`}
                    detail={`${analytics.action_items_completed}/${analytics.action_items} items`}
                  />
                  <IntelCard
                    label="Collaboration"
                    value={String(analytics.cross_team_pairs)}
                    detail={`${analytics.decisions} decisions · ${analytics.recordings} recordings`}
                  />
                </>
              )}
              {suggestions && suggestions.slots?.length > 0 && (
                <div className="card p-4 xl:col-span-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
                    Best times this week
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {suggestions.slots.slice(0, 3).map((slot) => (
                      <span
                        key={slot.start_at}
                        className="rounded-lg border border-line bg-canvas px-2.5 py-1 text-[12px] text-ink"
                      >
                        {formatDateTime(slot.start_at)}
                        <span className="ml-1.5 text-faint">
                          {slot.conflicts} conflicts
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          <section>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Radio className="h-4 w-4 text-danger" /> Live now
              <Badge tone="danger">{live.length}</Badge>
            </h2>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {live.map((meeting) => (
                <div
                  key={meeting.id}
                  className="card p-5 ring-1 ring-danger/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-danger/10 text-danger">
                      <Radio className="h-5 w-5" />
                    </div>
                    <Badge tone="danger">live</Badge>
                  </div>
                  <h3 className="mt-3 truncate font-semibold text-ink">
                    {meeting.title}
                  </h3>
                  <p className="text-[12px] text-faint">
                    {meeting.meeting_type.replace(/_/g, " ")} ·{" "}
                    {meeting.organizer_name ?? "No organizer"}
                  </p>
                  {meeting.session?.meeting_code && (
                    <p className="mt-2 font-mono text-[13px] font-semibold tracking-wider text-brand">
                      Code: {meeting.session.meeting_code}
                    </p>
                  )}
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-[12px] text-faint">
                      {meeting.session?.participants?.length ?? 0} in session
                    </span>
                    <Button size="sm" onClick={() => handleJoinNow(meeting)}>
                      <Play className="h-3.5 w-3.5" /> Join now
                    </Button>
                  </div>
                </div>
              ))}
              {live.length === 0 && (
                <p className="text-[13px] text-faint">
                  No meetings running right now.
                </p>
              )}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold text-ink">
              Upcoming <Badge tone="brand">{scheduled.length}</Badge>
            </h2>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {scheduled.map((meeting) => (
                <Link
                  key={meeting.id}
                  href={`/meetings/${meeting.id}`}
                  className="card group p-5 transition-shadow hover:shadow-popover"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
                      <Users className="h-5 w-5" />
                    </div>
                    <Badge tone={statusTone(meeting.status)}>
                      {meeting.status}
                    </Badge>
                  </div>
                  <h3 className="mt-3 truncate font-semibold text-ink group-hover:text-brand">
                    {meeting.title}
                  </h3>
                  <p className="text-[12px] text-faint">
                    {meeting.meeting_type.replace(/_/g, " ")} ·{" "}
                    {meeting.organizer_name ?? "No organizer"}
                  </p>
                  <p className="mt-2 text-[13px] font-medium text-muted">
                    {formatDateTime(meeting.start_at)}
                  </p>
                  {meeting.session?.meeting_code && (
                    <p className="mt-1 font-mono text-[12px] tracking-wider text-brand">
                      Code: {meeting.session.meeting_code}
                    </p>
                  )}
                </Link>
              ))}
              {scheduled.length === 0 && (
                <p className="text-[13px] text-faint">
                  Nothing scheduled
                  {scope !== "organization" ? ` in ${scope} scope` : ""}.
                </p>
              )}
            </div>
          </section>

          {completed.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold text-ink">
                Completed <Badge tone="success">{completed.length}</Badge>
              </h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {completed.map((meeting) => (
                  <Link
                    key={meeting.id}
                    href={`/meetings/${meeting.id}`}
                    className="card group p-5 transition-shadow hover:shadow-popover"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="truncate font-semibold text-ink group-hover:text-brand">
                        {meeting.title}
                      </h3>
                      <Badge tone={statusTone(meeting.status)}>
                        {meeting.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-[12px] text-faint">
                      {formatDateTime(meeting.start_at)} ·{" "}
                      {timeAgo(meeting.updated_at)}
                    </p>
                    {meeting.ai_summary && (
                      <p className="mt-2 line-clamp-2 text-[13px] text-muted">
                        {meeting.ai_summary}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Schedule meeting"
        description="Set the time, invite attendees and add an agenda."
        size="lg"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
              {formError}
            </div>
          )}
          <Input
            label="Title"
            name="title"
            required
            placeholder="Weekly product sync"
          />
          <Textarea label="Description" name="description" rows={2} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Type"
              name="meeting_type"
              defaultValue="team"
              options={MEETING_TYPES.map((t) => ({ value: t, label: t }))}
            />
            <Select
              label="Project"
              name="project_id"
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Start"
              name="start_at"
              type="datetime-local"
              required
            />
            <Input label="End" name="end_at" type="datetime-local" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Location" name="location" placeholder="Room 4" />
            <Input
              label="Meeting link"
              name="meeting_link"
              placeholder="https://meet.example.com/abc"
            />
          </div>
          <div>
            <p className="label">Attendees</p>
            <div className="max-h-40 overflow-y-auto rounded-lg border border-line p-2">
              {employees.length === 0 ? (
                <p className="px-2 py-3 text-[13px] text-faint">
                  No employees found.
                </p>
              ) : (
                employees.map((employee) => {
                  const selected = attendeeIds.includes(employee.id);
                  return (
                    <button
                      key={employee.id}
                      type="button"
                      onClick={() => toggleAttendee(employee.id)}
                      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] ${selected ? "bg-brand-soft text-brand" : "text-ink hover:bg-canvas"}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        readOnly
                        className="h-3.5 w-3.5 accent-brand"
                      />
                      {employee.full_name}
                      {employee.designation && (
                        <span className="ml-auto text-[11px] text-faint">
                          {employee.designation}
                        </span>
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Schedule meeting
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
