"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { Calendar, Clock, Users, Video, Settings, Plus, X, MoreHorizontal, FileText } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";
import { useMeeting } from "@/hooks/useMeeting";
import { Meeting, MeetingParticipant, AgendaItem, Material, Recording, ActionItem } from "@/types/meeting";
import { Transcript } from "@/types/transcript";

const MEETING_STATUS_LABELS: Record<string, string> = {
  scheduled: "Scheduled",
  active: "Active",
  ended: "Ended",
  cancelled: "Cancelled",
};

const MEETING_STATUS_TONES: Record<string, "neutral" | "brand" | "success" | "warning" | "danger"> = {
  scheduled: "brand",
  active: "success",
  ended: "neutral",
  cancelled: "danger",
};

const SCALE_LABELS: Record<string, string> = {
  small: "Small",
  team: "Team",
  department: "Department",
  town_hall: "Town Hall",
  webinar: "Webinar",
  conference: "Conference",
};

const MEETING_TYPE_LABELS: Record<string, string> = {
  standard: "Standard",
  standup: "Standup",
  planning: "Planning",
  review: "Review",
  one_on_one: "1:1",
  town_hall: "Town Hall",
  webinar: "Webinar",
  conference: "Conference",
};

export default function MeetingPage() {
  const router = useRouter();
  const params = useParams();
  const meetingId = params.meetingId as string;
  const { user } = useAuth();

  const {
    meeting,
    participants: meetingParticipants,
    recordings: meetingRecordings,
    agendaItems: meetingAgendaItems,
    materialsItems: meetingMaterialsItems,
    actionItems: meetingActionItems,
    transcripts: meetingTranscripts,
    settingsSummary,
    loading,
    error,
    joinMeeting,
    leaveMeeting,
    updateMeeting,
    deleteMeeting,
    addParticipant,
    removeParticipant,
    addAgendaItem,
    updateAgendaItem,
    deleteAgendaItem,
    addMaterial,
    removeMaterial,
    startRecording,
    stopRecording,
    addActionItem,
    updateActionItem,
    deleteActionItem,
  } = useMeeting({ meetingId, autoConnect: true });

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Loading meeting..." />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Failed to load meeting"
        message={error}
        onRetry={() => router.refresh()}
      />
    );
  }

  if (!meeting) {
    return (
      <EmptyState
        title="Meeting not found"
        description="This meeting doesn't exist or you don't have access to it."
      />
    );
  }

  const participants = meetingParticipants || [];
  const agendaItems = meetingAgendaItems || [];
  const materialsItems = meetingMaterialsItems || [];

  const OverviewContent = () => (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-6">
          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">Agenda</h2>
            </div>
            <div className="p-5">
              {agendaItems.length === 0 ? (
                <p className="text-muted text-center py-8">No agenda items yet</p>
              ) : (
                <ul className="space-y-3">
                  {agendaItems.map((item) => (
                    <li key={item.id} className="flex items-start gap-4 p-4 bg-muted/50 rounded-lg">
                      <div className="flex-shrink-0 w-10 h-10 rounded-full bg-brand/10 flex items-center justify-center text-brand">
                        {item.sort_order}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-ink truncate">{item.title}</h4>
                        <p className="text-sm text-muted mt-1">{item.description || "No description"}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">Materials</h2>
            </div>
            <div className="p-5">
              {materialsItems.length === 0 ? (
                <p className="text-muted text-center py-8">No materials yet</p>
              ) : (
                <ul className="space-y-3">
                  {materialsItems.map((material) => (
                    <li key={material.id} className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <FileText className="h-6 w-6 text-brand" />
                        <div>
                          <h4 className="font-medium truncate max-w-xs">{material.title}</h4>
                          <p className="text-sm text-muted">{material.type}</p>
                        </div>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => window.open(material.url, "_blank")}>
                        Open
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">Quick Stats</h2>
            </div>
            <div className="p-5 space-y-4">
              <div className="flex items-center gap-3 p-4 bg-canvas rounded-xl border border-line">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <Calendar className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs text-muted">Scheduled</p>
                  <p className="font-medium">
                    {meeting.scheduled_start
                      ? new Date(meeting.scheduled_start).toLocaleString()
                      : "Not scheduled"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-4 bg-canvas rounded-xl border border-line">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <Clock className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs text-muted">Duration</p>
                  <p className="font-medium">
                    {meeting.duration_minutes
                      ? `${meeting.duration_minutes} min`
                      : "Not set"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-4 bg-canvas rounded-xl border border-line">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <Users className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs text-muted">Participants</p>
                  <p className="font-medium">{participants.length} joined</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-4 bg-canvas rounded-xl border border-line">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <Video className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs text-muted">Type</p>
                  <p className="font-medium capitalize">{meeting.meeting_type}</p>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">Meeting Settings</h2>
            </div>
            <div className="p-5 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted">Recording</span>
                <span className="font-medium">{settingsSummary.recording ? "Enabled" : "Disabled"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted">Transcription</span>
                <span className="font-medium">{settingsSummary.transcription ? "Enabled" : "Disabled"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted">Waiting Room</span>
                <span className="font-medium">{settingsSummary.waitRoom ? "Enabled" : "Disabled"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted">Chat</span>
                <span className="font-medium">{settingsSummary.chat ? "Enabled" : "Disabled"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted">Reactions</span>
                <span className="font-medium">{settingsSummary.reactions ? "Enabled" : "Disabled"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted">Screen Share</span>
                <span className="font-medium">{settingsSummary.screenShare ? "Enabled" : "Disabled"}</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );

  const ParticipantsContent = () => (
    <Card>
      <div className="border-b border-line px-5 py-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Participants ({participants.length})</h2>
        <Button variant="secondary" size="sm" onClick={() => addParticipant({ email: "" })}>
          <Plus className="h-4 w-4 mr-1" />
          Invite
        </Button>
      </div>
      <div className="p-5">
        {participants.length === 0 ? (
          <p className="text-muted text-center py-8">No participants yet</p>
        ) : (
          <ul className="space-y-3">
            {participants.map((p) => (
              <li key={p.id} className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-full bg-brand/10 flex items-center justify-center text-brand">
                    {p.name?.charAt(0).toUpperCase() || p.email?.charAt(0).toUpperCase() || "?"}
                  </div>
                  <div>
                    <h4 className="font-medium text-ink">{p.name || p.email}</h4>
                    <p className="text-sm text-muted">{p.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <Badge tone={p.status === "joined" ? "success" : "neutral"} className="text-xs capitalize">
                    {p.status}
                  </Badge>
                  <Button variant="ghost" size="sm" className="p-1" onClick={() => removeParticipant(p.id)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );

  const RecordingsContent = () => (
    <Card>
      <div className="border-b border-line px-5 py-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Recordings</h2>
        <Button variant="secondary" size="sm" onClick={startRecording}>
          <Video className="h-4 w-4 mr-1" />
          Start Recording
        </Button>
      </div>
      <div className="p-5">
        {meetingRecordings.length === 0 ? (
          <p className="text-muted text-center py-8">No recordings yet</p>
        ) : (
          <ul className="space-y-4">
            {meetingRecordings.map((recording) => (
              <li key={recording.id} className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-lg bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <Video className="h-6 w-6 text-red-600 dark:text-red-400" />
                  </div>
                  <div>
                    <h4 className="font-medium truncate max-w-xs">{recording.title || "Untitled Recording"}</h4>
                    <p className="text-sm text-muted">
                      {recording.duration_seconds
                        ? `${Math.floor(recording.duration_seconds / 60)}:${String(recording.duration_seconds % 60).padStart(2, "0")}`
                        : "Processing..."}
                    </p>
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => window.open(recording.url, "_blank")}>
                  <FileText className="h-4 w-4 mr-1" />
                  Watch
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );

  const TranscriptsContent = () => (
    <Card>
      <div className="border-b border-line px-5 py-4">
        <h2 className="text-sm font-semibold text-ink">Transcript</h2>
      </div>
      <div className="p-5 max-h-[600px] overflow-y-auto">
        {meetingTranscripts.length === 0 ? (
          <p className="text-muted text-center py-8">No transcript available</p>
        ) : (
          <ul className="space-y-4">
            {meetingTranscripts.map((t) => (
              <li key={t.id} className="p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm">{t.speaker_name || "Unknown Speaker"}</span>
                  <span className="text-xs text-muted">
                    {new Date(t.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-sm text-ink">{t.content}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );

  const ActionItemsContent = () => (
    <Card>
      <div className="border-b border-line px-5 py-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Action Items</h2>
        <Button variant="secondary" size="sm" onClick={() => addActionItem({ title: "" })}>
          <Plus className="h-4 w-4 mr-1" />
          Add Action
        </Button>
      </div>
      <div className="p-5">
        {meetingActionItems.length === 0 ? (
          <p className="text-muted text-center py-8">No action items yet</p>
        ) : (
          <ul className="space-y-3">
            {meetingActionItems.map((item) => (
              <li key={item.id} className="flex items-start gap-4 p-4 bg-muted/50 rounded-lg">
                <input
                  type="checkbox"
                  checked={item.completed_at !== null}
                  onChange={() => updateActionItem(item.id, { completed_at: item.completed_at ? null : new Date().toISOString() })}
                  className="mt-1 h-4 w-4 rounded border-line text-brand focus:ring-brand"
                />
                <div className="flex-1 min-w-0">
                  <h4 className={`font-medium truncate ${item.completed_at ? "line-through text-muted" : "text-ink"}`}>{item.title}</h4>
                  <div className="flex items-center gap-4 mt-2 text-xs text-muted">
                    <span className="flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" />
                      {item.assignee_name || "Unassigned"}
                    </span>
                    {item.due_date && (
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3.5 w-3.5" />
                        {new Date(item.due_date).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );

  const SettingsContent = () => (
    <div className="p-5">
      <p className="text-muted">Settings coming soon...</p>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">{meeting.title}</h1>
          <p className="text-muted text-sm mt-1">{meeting.description || "No description"}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge tone={MEETING_STATUS_TONES[meeting.status] || "neutral"}>
            {MEETING_STATUS_LABELS[meeting.status] || meeting.status}
          </Badge>
          <Badge tone="neutral" className="text-xs">
            {SCALE_LABELS[meeting.scale] || meeting.scale}
          </Badge>
          <Badge tone="neutral" className="text-xs">
            {MEETING_TYPE_LABELS[meeting.meeting_type] || meeting.meeting_type}
          </Badge>
        </div>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-6 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="overview" className="py-2 flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="participants" className="py-2 flex items-center gap-2">
            <Users className="h-4 w-4" />
            Participants
          </TabsTrigger>
          <TabsTrigger value="recordings" className="py-2 flex items-center gap-2">
            <Video className="h-4 w-4" />
            Recordings
          </TabsTrigger>
          <TabsTrigger value="transcript" className="py-2 flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Transcript
          </TabsTrigger>
          <TabsTrigger value="actions" className="py-2 flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Actions
          </TabsTrigger>
          <TabsTrigger value="settings" className="py-2 flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <OverviewContent />
        </TabsContent>

        <TabsContent value="participants" className="space-y-6">
          <ParticipantsContent />
        </TabsContent>

        <TabsContent value="recordings" className="space-y-6">
          <RecordingsContent />
        </TabsContent>

        <TabsContent value="transcript" className="space-y-6">
          <TranscriptsContent />
        </TabsContent>

        <TabsContent value="actions" className="space-y-6">
          <ActionItemsContent />
        </TabsContent>

        <TabsContent value="settings" className="space-y-6">
          <SettingsContent />
        </TabsContent>
      </Tabs>
    </div>
  );
}