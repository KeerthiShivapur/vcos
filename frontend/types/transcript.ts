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

export type Transcript = MeetingTranscript;