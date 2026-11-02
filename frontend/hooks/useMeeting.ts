"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  Meeting,
  MeetingParticipant,
  AgendaItem,
  Material,
  Recording,
  ActionItem,
  Transcript,
} from "@/types";

interface UseMeetingOptions {
  meetingId: string;
  autoConnect?: boolean;
}

interface UseMeetingReturn {
  meeting: Meeting | null;
  participants: MeetingParticipant[];
  recordings: Recording[];
  agendaItems: AgendaItem[];
  materialsItems: Material[];
  actionItems: ActionItem[];
  transcripts: Transcript[];
  settingsSummary: {
    recording: boolean;
    transcription: boolean;
    waitRoom: boolean;
    chat: boolean;
    reactions: boolean;
    screenShare: boolean;
  };
  loading: boolean;
  error: string | null;
  joinMeeting: () => Promise<void>;
  leaveMeeting: () => Promise<void>;
  updateMeeting: (data: Partial<Meeting>) => Promise<void>;
  deleteMeeting: () => Promise<void>;
  addParticipant: (data: Partial<MeetingParticipant>) => Promise<void>;
  removeParticipant: (participantId: string) => Promise<void>;
  addAgendaItem: (data: Partial<AgendaItem>) => Promise<void>;
  updateAgendaItem: (id: string, data: Partial<AgendaItem>) => Promise<void>;
  deleteAgendaItem: (id: string) => Promise<void>;
  addMaterial: (data: Partial<Material>) => Promise<void>;
  removeMaterial: (materialId: string) => Promise<void>;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<void>;
  addActionItem: (data: Partial<ActionItem>) => Promise<void>;
  updateActionItem: (id: string, data: Partial<ActionItem>) => Promise<void>;
  deleteActionItem: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useMeeting({ meetingId, autoConnect = true }: UseMeetingOptions): UseMeetingReturn {
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [participants, setParticipants] = useState<MeetingParticipant[]>([]);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [agendaItems, setAgendaItems] = useState<AgendaItem[]>([]);
  const [materialsItems, setMaterialsItems] = useState<Material[]>([]);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMeeting = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [meetingData, participantsData, recordingsData, agendaData, materialsData, actionsData, transcriptsData] = await Promise.all([
        api<Meeting>(`/meetings/${meetingId}`),
        api<MeetingParticipant[]>(`/meetings/${meetingId}/participants`),
        api<Recording[]>(`/meetings/${meetingId}/recordings`),
        api<AgendaItem[]>(`/meetings/${meetingId}/agenda`),
        api<Material[]>(`/meetings/${meetingId}/materials`),
        api<ActionItem[]>(`/meetings/${meetingId}/action-items`),
        api<Transcript[]>(`/meetings/${meetingId}/transcripts`),
      ]);

      setMeeting(meetingData);
      setParticipants(participantsData);
      setRecordings(recordingsData);
      setAgendaItems(agendaData);
      setMaterialsItems(materialsData);
      setActionItems(actionsData);
      setTranscripts(transcriptsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load meeting");
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  const refresh = useCallback(async () => {
    await fetchMeeting();
  }, [fetchMeeting]);

  useEffect(() => {
    fetchMeeting();
  }, [fetchMeeting]);

  const joinMeeting = useCallback(async () => {
    try {
      await api(`/meetings/${meetingId}/join`, { method: "POST" });
      await fetchMeeting();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join meeting");
    }
  }, [meetingId, fetchMeeting]);

  const leaveMeeting = useCallback(async () => {
    try {
      await api(`/meetings/${meetingId}/leave`, { method: "POST" });
      await fetchMeeting();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to leave meeting");
    }
  }, [meetingId, fetchMeeting]);

  const updateMeeting = useCallback(async (data: Partial<Meeting>) => {
    try {
      const updated = await api<Meeting>(`/meetings/${meetingId}`, {
        method: "PATCH",
        body: data,
      });
      setMeeting(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update meeting");
    }
  }, [meetingId]);

  const deleteMeeting = useCallback(async () => {
    try {
      await api(`/meetings/${meetingId}`, { method: "DELETE" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete meeting");
    }
  }, [meetingId]);

  const addParticipant = useCallback(async (data: Partial<MeetingParticipant>) => {
    try {
      const participant = await api<MeetingParticipant>(`/meetings/${meetingId}/participants`, {
        method: "POST",
        body: data,
      });
      setParticipants((prev) => [...prev, participant]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add participant");
    }
  }, [meetingId]);

  const removeParticipant = useCallback(async (participantId: string) => {
    try {
      await api(`/meetings/${meetingId}/participants/${participantId}`, { method: "DELETE" });
      setParticipants((prev) => prev.filter((p) => p.id !== participantId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove participant");
    }
  }, [meetingId]);

  const addAgendaItem = useCallback(async (data: Partial<AgendaItem>) => {
    try {
      const item = await api<AgendaItem>(`/meetings/${meetingId}/agenda`, {
        method: "POST",
        body: data,
      });
      setAgendaItems((prev) => [...prev, item]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add agenda item");
    }
  }, [meetingId]);

  const updateAgendaItem = useCallback(async (id: string, data: Partial<AgendaItem>) => {
    try {
      const item = await api<AgendaItem>(`/meetings/${meetingId}/agenda/${id}`, {
        method: "PATCH",
        body: data,
      });
      setAgendaItems((prev) => prev.map((a) => (a.id === id ? item : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update agenda item");
    }
  }, [meetingId]);

  const deleteAgendaItem = useCallback(async (id: string) => {
    try {
      await api(`/meetings/${meetingId}/agenda/${id}`, { method: "DELETE" });
      setAgendaItems((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete agenda item");
    }
  }, [meetingId]);

  const addMaterial = useCallback(async (data: Partial<Material>) => {
    try {
      const material = await api<Material>(`/meetings/${meetingId}/materials`, {
        method: "POST",
        body: data,
      });
      setMaterialsItems((prev) => [...prev, material]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add material");
    }
  }, [meetingId]);

  const removeMaterial = useCallback(async (materialId: string) => {
    try {
      await api(`/meetings/${meetingId}/materials/${materialId}`, { method: "DELETE" });
      setMaterialsItems((prev) => prev.filter((m) => m.id !== materialId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove material");
    }
  }, [meetingId]);

  const startRecording = useCallback(async () => {
    try {
      await api(`/meetings/${meetingId}/recordings/start`, { method: "POST" });
      await fetchMeeting();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start recording");
    }
  }, [meetingId, fetchMeeting]);

  const stopRecording = useCallback(async () => {
    try {
      await api(`/meetings/${meetingId}/recordings/stop`, { method: "POST" });
      await fetchMeeting();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop recording");
    }
  }, [meetingId, fetchMeeting]);

  const addActionItem = useCallback(async (data: Partial<ActionItem>) => {
    try {
      const item = await api<ActionItem>(`/meetings/${meetingId}/action-items`, {
        method: "POST",
        body: data,
      });
      setActionItems((prev) => [...prev, item]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add action item");
    }
  }, [meetingId]);

  const updateActionItem = useCallback(async (id: string, data: Partial<ActionItem>) => {
    try {
      const item = await api<ActionItem>(`/meetings/${meetingId}/action-items/${id}`, {
        method: "PATCH",
        body: data,
      });
      setActionItems((prev) => prev.map((a) => (a.id === id ? item : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update action item");
    }
  }, [meetingId]);

  const deleteActionItem = useCallback(async (id: string) => {
    try {
      await api(`/meetings/${meetingId}/action-items/${id}`, { method: "DELETE" });
      setActionItems((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete action item");
    }
  }, [meetingId]);

  const settingsSummary = {
    recording: meeting?.recording_enabled ?? false,
    transcription: meeting?.transcription_enabled ?? false,
    waitRoom: meeting?.wait_room_enabled ?? false,
    chat: meeting?.chat_enabled ?? false,
    reactions: meeting?.reactions_enabled ?? false,
    screenShare: meeting?.screen_share_enabled ?? false,
  };

  return {
    meeting,
    participants,
    recordings,
    agendaItems,
    materialsItems,
    actionItems,
    transcripts,
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
    refresh,
  };
}