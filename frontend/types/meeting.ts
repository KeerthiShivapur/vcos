export type MeetingType =
  | "standard"
  | "standup"
  | "planning"
  | "review"
  | "one_on_one"
  | "town_hall"
  | "webinar"
  | "conference"
  | "board"
  | "interview"
  | "sales"
  | "support"
  | "training"
  | "workshop";

export type MeetingStatus =
  | "draft"
  | "scheduled"
  | "waiting"
  | "active"
  | "paused"
  | "ended"
  | "cancelled";

export type MeetingScale =
  "small" | "team" | "department" | "town_hall" | "webinar" | "conference";

export type ParticipantRole =
  | "host"
  | "co_host"
  | "presenter"
  | "participant"
  | "guest"
  | "observer";

export type ParticipantStatus =
  | "invited"
  | "pending"
  | "joining"
  | "joined"
  | "left"
  | "reconnecting";

export type RecordingStatus =
  "pending" | "recording" | "processing" | "completed" | "failed" | "expired";

export interface Meeting {
  id: string;
  title: string;
  description: string | null;
  meeting_type: MeetingType;
  scale: MeetingScale;
  status: MeetingStatus;
  organizer_id: string | null;
  organizer_name: string | null;
  project_id: string | null;
  goal_id: string | null;
  department_id?: string | null;
  team_id?: string | null;
  calendar_event_id?: string | null;
  room_id?: string | null;
  meeting_code?: string | null;
  timezone?: string | null;
  duration_minutes?: number | null;
  start_at: string | null;
  end_at: string | null;
  location: string | null;
  meeting_link: string | null;
  transcript_summary: string | null;
  ai_summary: string | null;
  created_at: string | null;
  updated_at: string | null;

  // Extended fields for native meetings (kept for backward compatibility)
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  actual_start?: string | null;
  actual_end?: string | null;
  agenda?: string[];
  materials?: any[];
  settings?: Record<string, any>;
  recording_enabled?: boolean;
  transcription_enabled?: boolean;
  wait_room_enabled?: boolean;
  chat_enabled?: boolean;
  reactions_enabled?: boolean;
  screen_share_enabled?: boolean;
  require_approval?: boolean;
  allow_external_guests?: boolean;
  password_protected?: boolean;
  password_hash?: string | null;
  recording_id?: string | null;
  recording_url?: string | null;
  recording_status?: string | null;
  transcription_url?: string | null;
  transcription_status?: string | null;
  current_presentation_id?: string | null;
  presentation_state?: Record<string, any>;
  decisions?: any[];
  action_items?: any[];
  summary?: string | null;
  summary_generated_at?: string | null;
  created_by?: string | null;
  started_by?: string | null;
  ended_by?: string | null;
  scheduled_duration_minutes?: number | null;
}

export interface MeetingRoom {
  id: string;
  name: string;
  room_type: string;
  description: string | null;
  capacity: number;
  location: string | null;
  status: string;
  department_id: string | null;
  team_id: string | null;
  project_id: string | null;
  created_by: string | null;
  is_public: boolean;
  allow_recording: boolean;
  settings: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface MeetingParticipant {
  id: string;
  meeting_id: string;
  user_id?: string | null;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  role: ParticipantRole;
  status: ParticipantStatus;
  duration_seconds: number;
  audio_enabled: boolean;
  video_enabled: boolean;
  screen_sharing: boolean;
  hand_raised: boolean;
  joined_at?: string | null;
  left_at?: string | null;
  raised_hand: boolean;

  // Extended fields for backend compatibility
  session_id?: string;
  employee_id?: string;
  name?: string | null;
  designation?: string | null;
  avatar_url?: string | null;
  role?: string;
  status?: string;
  device?: string | null;
  mic_enabled?: boolean;
  camera_enabled?: boolean;
  screen_sharing?: boolean;
  is_present?: boolean;
  joined_at?: string | null;
  left_at?: string | null;
  last_active_at?: string | null;
  speaking_seconds?: number;
  messages_count?: number;
  raised_hand?: boolean;
}

export interface MeetingSession {
  id: string;
  meeting_id: string;
  room_id: string | null;
  status: string;
  meeting_code: string;
  timezone: string;
  max_participants: number;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number;
  is_recording: boolean;
  is_captions_enabled: boolean;
  is_translation_enabled: boolean;
  is_transcribing: boolean;
  settings: Record<string, unknown> | null;
  participants: MeetingParticipant[];
  created_at: string | null;
  updated_at: string | null;
}

export interface MeetingWithSession extends Meeting {
  session?: MeetingSession | null;
}

export interface MeetingNote {
  id: string;
  meeting_id: string;
  session_id: string | null;
  author_id: string | null;
  author_name: string | null;
  content: string;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface Attendee {
  id: string;
  employee_id: string;
  name: string;
  designation: string | null;
  avatar_url: string | null;
  role: string;
  status: string;
  rsvp_at: string | null;
}

export interface AgendaItem {
  id: string;
  meeting_id: string;
  title: string;
  description: string | null;
  sort_order: number;
  duration_minutes: number | null;
  notes: string | null;
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  title: string;
  assignee_id: string | null;
  assignee_name: string | null;
  due_date: string | null;
  status: string;
  completed_at: string | null;
  created_at: string | null;
}

export interface Material {
  id: string;
  meeting_id: string;
  title: string;
  description: string | null;
  url: string;
  type: string;
  size_bytes: number | null;
  mime_type: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Recording {
  id: string;
  meeting_id: string;
  session_id: string | null;
  room_id: string | null;
  title: string;
  kind: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number;
  file_url: string | null;
  storage_key: string | null;
  size_bytes: number;
  format: string | null;
  mime_type: string | null;
  resolution: string | null;
  captions_enabled: boolean;
  language: string;
  visibility: string;
  retention_days: number;
  is_encrypted: boolean;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  meeting_title?: string | null;
  meeting_status?: string | null;
}

export interface MeetingDecision {
  id: string;
  meeting_id: string;
  session_id: string | null;
  content: string;
  made_by: string | null;
  source: string;
  status: string;
  created_at: string | null;
}

export interface MeetingAttendance {
  duration_seconds: number;
  participants_invited: number;
  participants_joined: number;
  participants_present: number;
  late_joiners: string[];
  early_exits: string[];
  with_mic: number;
  with_camera: number;
  screen_shares: number;
  raised_hands: number;
  messages_count: number;
  speaking_seconds: number;
  engagement_score: number;
}

export interface MeetingAttendanceResponse {
  live: MeetingAttendance;
  snapshot: {
    id: string;
    meeting_id: string;
    engagement_score: number;
    metrics: Record<string, unknown>;
  } | null;
}

export interface MeetingSuggestion {
  start_at: string;
  end_at: string;
  conflicts: number;
  room_ids: string[];
}

export interface MeetingSuggestionsResponse {
  slots: MeetingSuggestion[];
  rooms: Record<string, unknown>[];
  timezones: Record<string, unknown>[];
}

export interface MeetingAnalyticsOverview {
  period_days: number;
  meetings_total: number;
  meetings_completed: number;
  meetings_cancelled: number;
  time_in_meetings_hours: number;
  avg_duration_minutes: number;
  avg_engagement_score: number;
  action_items: number;
  action_items_completed: number;
  action_completion_rate: number;
  decisions: number;
  notes: number;
  recordings: number;
  cross_team_pairs: number;
  meetings_per_week: Record<string, number>;
  recent: {
    id: string;
    title: string;
    status: string;
    created_at: string | null;
  }[];
}

export interface MeetingTranscript {
  id: string;
  meeting_id: string;
  session_id: string | null;
  status: string;
  language: string;
  content: string;
  segments: Record<string, unknown>[];
  speakers: Record<string, unknown>[];
  word_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface MeetingParticipant {
  id: string;
  meeting_id: string;
  user_id?: string | null;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  role: ParticipantRole;
  status: ParticipantStatus;
  duration_seconds: number;
  audio_enabled: boolean;
  video_enabled: boolean;
  screen_sharing: boolean;
  hand_raised: boolean;
  joined_at?: string | null;
  left_at?: string | null;
  raised_hand: boolean;

  // Extended fields for backend compatibility
  session_id?: string;
  employee_id?: string;
  name?: string | null;
  designation?: string | null;
  avatar_url?: string | null;
  role?: string;
  status?: string;
  device?: string | null;
  mic_enabled?: boolean;
  camera_enabled?: boolean;
  screen_sharing?: boolean;
  is_present?: boolean;
  joined_at?: string | null;
  left_at?: string | null;
  last_active_at?: string | null;
  speaking_seconds?: number;
  messages_count?: number;
  raised_hand?: boolean;
}

export interface MeetingSession {
  id: string;
  meeting_id: string;
  room_id: string | null;
  status: string;
  meeting_code: string;
  timezone: string;
  max_participants: number;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number;
  is_recording: boolean;
  is_captions_enabled: boolean;
  is_translation_enabled: boolean;
  is_transcribing: boolean;
  settings: Record<string, unknown> | null;
  participants: MeetingParticipant[];
  created_at: string | null;
  updated_at: string | null;
}

export interface MeetingWithSession extends Meeting {
  session?: MeetingSession | null;
}

export interface MeetingNote {
  id: string;
  meeting_id: string;
  session_id: string | null;
  author_id: string | null;
  author_name: string | null;
  content: string;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface Attendee {
  id: string;
  employee_id: string;
  name: string;
  designation: string | null;
  avatar_url: string | null;
  role: string;
  status: string;
  rsvp_at: string | null;
}

export interface AgendaItem {
  id: string;
  meeting_id: string;
  title: string;
  description: string | null;
  sort_order: number;
  duration_minutes: number | null;
  notes: string | null;
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  title: string;
  assignee_id: string | null;
  assignee_name: string | null;
  due_date: string | null;
  status: string;
  completed_at: string | null;
  created_at: string | null;
}

export interface Material {
  id: string;
  meeting_id: string;
  title: string;
  description: string | null;
  url: string;
  type: string;
  size_bytes: number | null;
  mime_type: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Recording {
  id: string;
  meeting_id: string;
  session_id: string | null;
  room_id: string | null;
  title: string;
  kind: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number;
  file_url: string | null;
  storage_key: string | null;
  size_bytes: number;
  format: string | null;
  mime_type: string | null;
  resolution: string | null;
  captions_enabled: boolean;
  language: string;
  visibility: string;
  retention_days: number;
  is_encrypted: boolean;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  meeting_title?: string | null;
  meeting_status?: string | null;
}

export interface MeetingDecision {
  id: string;
  meeting_id: string;
  session_id: string | null;
  content: string;
  made_by: string | null;
  source: string;
  status: string;
  created_at: string | null;
}

export interface MeetingAttendance {
  duration_seconds: number;
  participants_invited: number;
  participants_joined: number;
  participants_present: number;
  late_joiners: string[];
  early_exits: string[];
  with_mic: number;
  with_camera: number;
  screen_shares: number;
  raised_hands: number;
  messages_count: number;
  speaking_seconds: number;
  engagement_score: number;
}

export interface MeetingAttendanceResponse {
  live: MeetingAttendance;
  snapshot: {
    id: string;
    meeting_id: string;
    engagement_score: number;
    metrics: Record<string, unknown>;
  } | null;
}

export interface MeetingSuggestion {
  start_at: string;
  end_at: string;
  conflicts: number;
  room_ids: string[];
}

export interface MeetingSuggestionsResponse {
  slots: MeetingSuggestion[];
  rooms: Record<string, unknown>[];
  timezones: Record<string, unknown>[];
}

export interface MeetingAnalyticsOverview {
  period_days: number;
  meetings_total: number;
  meetings_completed: number;
  meetings_cancelled: number;
  time_in_meetings_hours: number;
  avg_duration_minutes: number;
  avg_engagement_score: number;
  action_items: number;
  action_items_completed: number;
  action_completion_rate: number;
  decisions: number;
  notes: number;
  recordings: number;
  cross_team_pairs: number;
  meetings_per_week: Record<string, number>;
  recent: {
    id: string;
    title: string;
    status: string;
    created_at: string | null;
  }[];
}

export interface MeetingTranscript {
  id: string;
  meeting_id: string;
  session_id: string | null;
  status: string;
  language: string;
  content: string;
  segments: Record<string, unknown>[];
  speakers: Record<string, unknown>[];
  word_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export type MeetingType =
  | "standard"
  | "standup"
  | "planning"
  | "review"
  | "one_on_one"
  | "town_hall"
  | "webinar"
  | "conference"
  | "board"
  | "interview"
  | "sales"
  | "support"
  | "training"
  | "workshop";

export type MeetingStatus =
  | "draft"
  | "scheduled"
  | "waiting"
  | "active"
  | "paused"
  | "ended"
  | "cancelled";

export type MeetingScale =
  "small" | "team" | "department" | "town_hall" | "webinar" | "conference";

export type ParticipantRole =
  | "host"
  | "co_host"
  | "presenter"
  | "participant"
  | "guest"
  | "observer";

export type ParticipantStatus =
  | "invited"
  | "pending"
  | "joining"
  | "joined"
  | "left"
  | "reconnecting";

export type RecordingStatus =
  "pending" | "recording" | "processing" | "completed" | "failed" | "expired";