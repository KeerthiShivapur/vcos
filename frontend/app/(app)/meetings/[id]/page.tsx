"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CalendarClock, CheckCircle2, ClipboardList, ListChecks, Plus, Radio, Sparkles, Trash2 } from "lucide-react";

import {
  addActionItem,
  addAgendaItem,
  addMeetingAttendee,
  completeActionItem,
  completeMeeting,
  endMeetingSession,
  getMeeting,
  getMeetingSession,
  getMyEmployee,
  joinMeeting,
  leaveMeeting,
  listActionItems,
  listAgendaItems,
  listEmployees,
  listMeetingAttendees,
  removeMeetingAttendee,
  rsvpMeeting,
  sendMeetingPresence,
  startMeetingSession,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { ActionItem, AgendaItem, Attendee, EmployeeSummary, Meeting, MeetingParticipant, MeetingSession } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDateTime, formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import { Tabs } from "@/components/ui/Tabs";
import { LivePanel } from "@/components/meeting/LivePanel";
import { IntelligencePanel } from "@/components/meeting/IntelligencePanel";

export default function MeetingDetailPage() {
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
  const canManage = roleCan(user?.role, PERMISSIONS.MEETINGS_MANAGE);

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [attendees, setAttendees] = useState<Attendee[]>([]);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [session, setSession] = useState<MeetingSession | null>(null);
  const [participants, setParticipants] = useState<MeetingParticipant[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);
  const [inSession, setInSession] = useState(false);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showAddAttendee, setShowAddAttendee] = useState(false);
  const [showAddAgenda, setShowAddAgenda] = useState(false);
  const [showAddAction, setShowAddAction] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "live" | "intel">("overview");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [meetingData, attendeeList, agendaList, actionList, empList, me, sessionData] = await Promise.all([
        getMeeting(id),
        listMeetingAttendees(id),
        listAgendaItems(id),
        listActionItems(id),
        listEmployees({ page_size: 200 }),
        getMyEmployee().catch(() => null),
        getMeetingSession(id).catch(() => null),
      ]);
      setMeeting(meetingData);
      setAttendees(attendeeList);
      setAgenda(agendaList);
      setActionItems(actionList);
      setEmployees(empList);
      setMyEmployeeId(me?.id ?? null);
      if (sessionData) {
        setSession(sessionData);
        setParticipants(sessionData.participants ?? []);
        setInSession((sessionData.participants ?? []).some((p) => p.employee_id === me?.id && p.status === "joined"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load meeting");
    } finally {
      setLoading(false);
    }
  }

  async function refreshSession() {
    const sessionData = await getMeetingSession(id).catch(() => null);
    if (sessionData) {
      setSession(sessionData);
      setParticipants(sessionData.participants ?? []);
      if (myEmployeeId) {
        setInSession(sessionData.participants.some((p) => p.employee_id === myEmployeeId && p.status === "joined"));
      }
    }
  }

  async function handleJoinSession() {
    try {
      const result = await joinMeeting(id, "desktop");
      setSession(result.session);
      setParticipants(result.session.participants ?? []);
      setInSession(true);
      toastSuccess(`You joined "${result.meeting.title}"`);
      await sendMeetingPresence(id, { mic_enabled: micOn, camera_enabled: camOn });
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to join the session");
    }
  }

  async function handleLeaveSession() {
    try {
      await leaveMeeting(id);
      setInSession(false);
      toastSuccess("You left the session");
      await refreshSession();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to leave the session");
    }
  }

  async function toggleMedia(kind: "mic" | "cam") {
    const nextMic = kind === "mic" ? !micOn : micOn;
    const nextCam = kind === "cam" ? !camOn : camOn;
    if (kind === "mic") setMicOn(nextMic);
    else setCamOn(nextCam);
    if (inSession) {
      try {
        await sendMeetingPresence(id, { mic_enabled: nextMic, camera_enabled: nextCam });
      } catch {
        // presence is best-effort
      }
    }
  }

  async function handleStartSession() {
    try {
      const sessionData = await startMeetingSession(id);
      setSession(sessionData);
      toastSuccess("Session started — share the code to invite people");
      await handleJoinSession();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to start the session");
    }
  }

  async function handleEndSession() {
    try {
      const sessionData = await endMeetingSession(id);
      setSession(sessionData);
      setInSession(false);
      toastSuccess("Session ended");
      const fresh = await getMeeting(id);
      setMeeting(fresh);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to end the session");
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleRsvp(status: "accepted" | "declined" | "tentative") {
    try {
      await rsvpMeeting(id, status);
      toastSuccess(`RSVP set to ${status}`);
      const [attendeeList, fresh] = await Promise.all([listMeetingAttendees(id), getMeeting(id)]);
      setAttendees(attendeeList);
      setMeeting(fresh);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to update RSVP");
    }
  }

  async function handleAddAttendee(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const employeeId = String(form.get("employee_id") ?? "");
    if (!employeeId) return;
    setSaving(true);
    setFormError(null);
    try {
      await addMeetingAttendee(id, employeeId, String(form.get("role") ?? "") || undefined);
      toastSuccess("Attendee added");
      setShowAddAttendee(false);
      setAttendees(await listMeetingAttendees(id));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to add attendee");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveAttendee(employeeId: string) {
    try {
      await removeMeetingAttendee(id, employeeId);
      toastSuccess("Attendee removed");
      setAttendees(await listMeetingAttendees(id));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to remove attendee");
    }
  }

  async function handleAddAgenda(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) return;
    setSaving(true);
    setFormError(null);
    try {
      await addAgendaItem(id, {
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        duration_minutes: form.get("duration_minutes") ? Number(form.get("duration_minutes")) : undefined,
      });
      toastSuccess("Agenda item added");
      setShowAddAgenda(false);
      setAgenda(await listAgendaItems(id));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to add agenda item");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) return;
    setSaving(true);
    setFormError(null);
    try {
      await addActionItem(id, {
        title,
        assignee_id: String(form.get("assignee_id") ?? "") || undefined,
        due_date: String(form.get("due_date") ?? "") ? new Date(String(form.get("due_date"))).toISOString() : undefined,
      });
      toastSuccess("Action item added");
      setShowAddAction(false);
      setActionItems(await listActionItems(id));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to add action item");
    } finally {
      setSaving(false);
    }
  }

  async function handleCompleteAction(itemId: string) {
    try {
      const updated = await completeActionItem(id, itemId);
      setActionItems((items) => items.map((i) => (i.id === itemId ? updated : i)));
      toastSuccess("Action item completed");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to complete action item");
    }
  }

  async function handleCompleteMeeting() {
    setCompleting(true);
    try {
      const updated = await completeMeeting(id);
      setMeeting(updated);
      toastSuccess("Meeting completed");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to complete meeting");
    } finally {
      setCompleting(false);
    }
  }

  if (error) return <ErrorState title="Could not load meeting" message={error} />;
  if (loading || !meeting) return <div className="flex justify-center py-24"><Spinner label="Loading meeting" /></div>;

  const myRsvp = myEmployeeId ? attendees.find((a) => a.employee_id === myEmployeeId) : null;
  const openActions = actionItems.filter((a) => a.status !== "completed").length;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Meetings"
        title={meeting.title}
        description={meeting.description ?? `${meeting.meeting_type.replace(/_/g, " ")} meeting`}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
            {canManage && meeting.status === "scheduled" && (
              <Button size="sm" loading={completing} onClick={handleCompleteMeeting}>
                <CheckCircle2 className="h-4 w-4" /> Complete meeting
              </Button>
            )}
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card p-4">
          <p className="text-xs font-medium text-faint">When</p>
          <p className="mt-1 text-[13px] font-semibold text-ink">{formatDateTime(meeting.start_at)}</p>
          {meeting.end_at && <p className="text-[12px] text-faint">until {formatDateTime(meeting.end_at)}</p>}
        </div>
        <div className="card p-4">
          <p className="text-xs font-medium text-faint">Organizer</p>
          <p className="mt-1 text-[13px] font-semibold text-ink">{meeting.organizer_name ?? "—"}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-medium text-faint">Where</p>
          <p className="mt-1 truncate text-[13px] font-semibold text-ink">{meeting.location ?? meeting.meeting_link ?? "—"}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-medium text-faint">Action items</p>
          <p className="mt-1 text-[13px] font-semibold text-ink">{openActions} open · {actionItems.length} total</p>
        </div>
      </div>

      {myEmployeeId && (
        <Card title="Your RSVP">
          <div className="flex flex-wrap gap-2">
            {(["accepted", "tentative", "declined"] as const).map((status) => (
              <Button
                key={status}
                size="sm"
                variant={myRsvp?.status === status ? "primary" : "secondary"}
                onClick={() => handleRsvp(status)}
              >
                {myRsvp ? `Change to ${status}` : status}
              </Button>
            ))}
            {myRsvp && <span className="flex items-center text-[13px] text-muted">Current: {myRsvp.status}</span>}
          </div>
        </Card>
      )}

      {(session || canManage) && (
        <Card
          title={session ? `Live session — ${session.status}` : "Live session"}
          subtitle={session ? `Join code ${session.meeting_code} · ${participants.length} in session` : "Start a session to open this meeting to live participants."}
        >
          <div className="flex flex-wrap items-center gap-3">
            {session?.meeting_code && (
              <div className="flex items-center gap-2 rounded-lg border border-line bg-canvas px-3 py-2">
                <span className="text-[12px] font-medium text-faint">Code</span>
                <span className="font-mono text-[14px] font-bold tracking-[0.2em] text-brand">{session.meeting_code}</span>
              </div>
            )}
            {!inSession ? (
              <Button size="sm" onClick={handleJoinSession}>
                Join session
              </Button>
            ) : (
              <>
                <Button size="sm" variant={micOn ? "primary" : "secondary"} onClick={() => toggleMedia("mic")}>
                  {micOn ? "Mic on" : "Mic off"}
                </Button>
                <Button size="sm" variant={camOn ? "primary" : "secondary"} onClick={() => toggleMedia("cam")}>
                  {camOn ? "Camera on" : "Camera off"}
                </Button>
                <Button size="sm" variant="ghost" onClick={handleLeaveSession}>
                  Leave
                </Button>
              </>
            )}
            {canManage && !session && (
              <Button size="sm" variant="secondary" onClick={handleStartSession}>
                Start session
              </Button>
            )}
            {canManage && session?.status === "live" && (
              <Button size="sm" variant="ghost" onClick={handleEndSession}>
                End session
              </Button>
            )}
            {session?.status === "live" && <Badge tone="danger">live</Badge>}
          </div>

          {participants.length > 0 && (
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {participants.map((participant) => (
                <div key={participant.id} className="flex items-center gap-2.5 rounded-lg border border-line p-2.5">
                  <div className="relative">
                    <Avatar name={participant.name ?? "?"} size="sm" />
                    <span
                      className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white ${participant.is_present ? "bg-success" : "bg-faint"}`}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{participant.name ?? "Unknown"}</p>
                    <p className="text-[11px] text-faint">
                      {participant.role}
                      {participant.speaking_seconds ? ` · ${Math.round(participant.speaking_seconds / 60)}m speaking` : ""}
                    </p>
                  </div>
                  {participant.mic_enabled && <Badge tone="neutral">mic</Badge>}
                  {participant.raised_hand && <Badge tone="warning">hand</Badge>}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <Tabs
        tabs={[
          { id: "overview", label: "Overview", count: actionItems.length + attendees.length, icon: ClipboardList },
          { id: "live", label: "Live", icon: Radio },
          { id: "intel", label: "Intelligence", icon: Sparkles },
        ]}
        active={activeTab}
        onChange={(id) => setActiveTab(id as "overview" | "live" | "intel")}
      />

      {activeTab === "overview" && (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Attendees" subtitle={`${attendees.length} invited`}
          actions={canManage ? <Button size="sm" variant="secondary" onClick={() => setShowAddAttendee(true)}><Plus className="h-3.5 w-3.5" /> Add</Button> : undefined}>
          {attendees.length === 0 ? (
            <EmptyState icon={CalendarClock} title="No attendees" />
          ) : (
            <ul className="space-y-2.5">
              {attendees.map((attendee) => (
                <li key={attendee.id} className="flex items-center gap-2.5">
                  <Avatar name={attendee.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{attendee.name}</p>
                    <p className="truncate text-[11px] text-faint">{attendee.designation ?? attendee.role}</p>
                  </div>
                  <Badge tone={attendee.status === "accepted" ? "success" : attendee.status === "declined" ? "danger" : "warning"}>{attendee.status}</Badge>
                  {canManage && myEmployeeId !== attendee.employee_id && (
                    <button onClick={() => handleRemoveAttendee(attendee.employee_id)} className="rounded-lg p-1 text-faint hover:bg-danger/10 hover:text-danger" title="Remove attendee">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Agenda" subtitle={`${agenda.length} items`}
          actions={canManage ? <Button size="sm" variant="secondary" onClick={() => setShowAddAgenda(true)}><Plus className="h-3.5 w-3.5" /> Add</Button> : undefined}>
          {agenda.length === 0 ? (
            <EmptyState icon={ClipboardList} title="No agenda" description="Add topics to structure the meeting." />
          ) : (
            <ol className="space-y-2.5">
              {agenda.map((item, index) => (
                <li key={item.id} className="flex items-start gap-3 rounded-lg border border-line p-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-soft text-[11px] font-semibold text-brand">{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-ink">{item.title}</p>
                    {item.description && <p className="text-[12px] text-muted">{item.description}</p>}
                  </div>
                  {item.duration_minutes && <span className="shrink-0 text-[11px] text-faint">{item.duration_minutes}m</span>}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <Card title="Action items" subtitle="What comes out of this meeting"
        actions={canManage ? <Button size="sm" variant="secondary" onClick={() => setShowAddAction(true)}><Plus className="h-3.5 w-3.5" /> Add</Button> : undefined}>
        {actionItems.length === 0 ? (
          <EmptyState icon={ListChecks} title="No action items" />
        ) : (
          <ul className="space-y-2.5">
            {actionItems.map((item) => (
              <li key={item.id} className={`flex items-center gap-3 rounded-lg border border-line p-3 ${item.status === "completed" ? "opacity-60" : ""}`}>
                {canManage && item.status !== "completed" ? (
                  <button onClick={() => handleCompleteAction(item.id)} className="rounded-full border border-line p-1 text-faint hover:border-success hover:text-success" title="Complete">
                    <CheckCircle2 className="h-4 w-4" />
                  </button>
                ) : (
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-success" />
                )}
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-[13px] font-medium ${item.status === "completed" ? "text-muted line-through" : "text-ink"}`}>{item.title}</p>
                  <p className="text-[11px] text-faint">
                    {item.assignee_name ?? "Unassigned"}
                    {item.due_date ? ` · due ${formatDate(item.due_date)}` : ""}
                  </p>
                </div>
                <Badge tone={item.status === "completed" ? "success" : "warning"}>{item.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {(meeting.ai_summary || meeting.transcript_summary) && (
        <Card title="Summary" subtitle="Generated after the meeting">
          <p className="whitespace-pre-line text-[13px] leading-relaxed text-muted">{meeting.ai_summary ?? meeting.transcript_summary}</p>
        </Card>
      )}
        </>
      )}

      {activeTab === "live" && (
        session?.status === "live" ? (
          <LivePanel
            meetingId={id}
            myEmployeeId={myEmployeeId}
            isHost={canManage}
            recordingState={session ? { is_recording: session.is_recording, started_at: session.started_at } : undefined}
          />
        ) : (
          <Card title="Live room">
            <EmptyState
              icon={Radio}
              title="No live session"
              description="Start or join a session to open chat, the whiteboard, captions and recording controls."
            />
          </Card>
        )
      )}

      {activeTab === "intel" && (
        <IntelligencePanel
          meetingId={id}
          canManage={canManage}
          onFinalized={async () => {
            try {
              setMeeting(await getMeeting(id));
            } catch {
              /* summary refresh is best-effort */
            }
          }}
        />
      )}

      <Modal open={showAddAttendee} onClose={() => setShowAddAttendee(false)} title="Add attendee">
        <form onSubmit={handleAddAttendee} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Select label="Employee" name="employee_id" required options={employees
            .filter((e) => !attendees.some((a) => a.employee_id === e.id))
            .map((e) => ({ value: e.id, label: `${e.full_name} — ${e.designation ?? ""}` }))} />
          <Select label="Role" name="role" options={["participant", "presenter", "organizer", "note_taker"].map((r) => ({ value: r, label: r }))} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowAddAttendee(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Add attendee</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showAddAgenda} onClose={() => setShowAddAgenda(false)} title="Add agenda item">
        <form onSubmit={handleAddAgenda} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Title" name="title" required placeholder="Roadmap review" />
          <Input label="Description" name="description" />
          <Input label="Duration (minutes)" name="duration_minutes" type="number" min={1} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowAddAgenda(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Add item</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showAddAction} onClose={() => setShowAddAction(false)} title="Add action item">
        <form onSubmit={handleAddAction} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Title" name="title" required placeholder="Send the design files" />
          <Select label="Assignee" name="assignee_id" options={employees.map((e) => ({ value: e.id, label: e.full_name }))} />
          <Input label="Due date" name="due_date" type="date" />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowAddAction(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Add action item</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
