/**
 * Collaboration Types
 * Type definitions for real-time collaboration features
 */

// CRDT Types
export type CRDTType = "ytext" | "yarray" | "ymap" | "counter" | "awareness";
export type OperationType = "insert" | "delete" | "update" | "retain";

export interface CRDTOperation {
  id: string;
  crdtType: CRDTType;
  docId: string;
  clientId: string;
  operationType: OperationType;
  position: number;
  content?: string | any;
  length?: number;
  attributes?: Record<string, any>;
  timestamp: number;
  vectorClock: Record<string, number>;
}

export interface CRDTDocument {
  docId: string;
  crdtType: CRDTType;
  state: any;
  version: number;
  clients: Map<
    string,
    {
      cursor?: { x: number; y: number };
      selection?: { start: number; end: number };
      userName: string;
      userColor: string;
      status: "online" | "idle" | "away" | "offline";
      lastActive: number;
    }
  >;
  pendingOps: CRDTOperation[];
  appliedOps: Set<string>;
  lastModified: number;
  lastModifiedBy: string;
}

export interface AwarenessState {
  clientId: string;
  userId: string;
  userName: string;
  userColor: string;
  cursor?: { x: number; y: number };
  selection?: { start: number; end: number };
  status: "online" | "idle" | "away" | "offline";
  lastActive: number;
  metadata: Record<string, any>;
}

// Comment & Annotation Types
export interface CommentAnchor {
  // For text documents
  position?: number;
  length?: number;
  // For spreadsheets/grids
  cell?: string;
  // For whiteboards
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

export interface CommentReaction {
  emoji: string;
  userIds: string[];
}

export interface CommentAttachment {
  id: string;
  name: string;
  url: string;
  type: string;
  size: number;
}

export interface Comment {
  id: string;
  threadId: string;
  parentId?: string;
  documentId: string;
  anchor: CommentAnchor;
  authorId: string;
  authorName: string;
  authorColor: string;
  content: string;
  createdAt: number;
  updatedAt: number;
  resolved: boolean;
  reactions: Record<string, string[]>; // emoji -> userIds[]
  mentions: string[];
  attachments: CommentAttachment[];
}

export interface CommentThread {
  id: string;
  documentId: string;
  anchor: CommentAnchor;
  comments: Comment[];
  resolved: boolean;
  createdAt: number;
  updatedAt: number;
  createdBy: string;
  assignedTo?: string;
  labels: string[];
}

// WebRTC / Call Types
export type CallType = "audio" | "video" | "screen_share" | "conference";
export type CallState =
  | "idle"
  | "initiated"
  | "ringing"
  | "connecting"
  | "connected"
  | "hold"
  | "ended"
  | "failed"
  | "rejected";

export interface CallParticipant {
  identity: string;
  name: string;
  isLocal: boolean;
  hasVideo: boolean;
  hasAudio: boolean;
  videoEnabled: boolean;
  audioEnabled: boolean;
  screenShareEnabled: boolean;
  connectionQuality: "good" | "poor" | "lost";
  isSpeaking: boolean;
  color?: string;
}

export interface CallSettings {
  maxParticipants: number;
  recordingEnabled: boolean;
  screenShareEnabled: boolean;
  chatEnabled: boolean;
  lobbyEnabled: boolean;
}

export interface Call {
  callId: string;
  callType: CallType;
  state: CallState;
  creatorId: string;
  participants: Map<string, CallParticipant>;
  createdAt: number;
  startedAt?: number;
  endedAt?: number;
  maxParticipants: number;
  recording: boolean;
  recordingId?: string;
  recordingStartedAt?: number;
  settings: CallSettings;
  livekitRoomName?: string;
  livekitRoomSid?: string;
}

// Signaling Types
export type SignalingMessageType =
  | "offer"
  | "answer"
  | "ice_candidate"
  | "join"
  | "leave"
  | "call_init"
  | "call_accept"
  | "call_reject"
  | "call_end"
  | "call_hold"
  | "call_resume"
  | "mute"
  | "unmute"
  | "screen_share_start"
  | "screen_share_stop"
  | "recording_start"
  | "recording_stop"
  | "participant_joined"
  | "participant_left"
  | "error";

export interface SignalingMessage {
  type: SignalingMessageType;
  callId: string;
  fromUser: string;
  toUser?: string;
  payload: Record<string, any>;
  timestamp: number;
}

// Screen Share Types
export interface ScreenShareOptions {
  video?: boolean;
  audio?: boolean;
  preferCurrentTab?: boolean;
  selfBrowserSurface?: "include" | "exclude";
  systemAudio?: "include" | "exclude";
  surfaceSwitching?: "include" | "exclude";
  monitorTypeSurfaces?: "include" | "exclude";
}

export interface ScreenShareState {
  isSharing: boolean;
  stream: MediaStream | null;
  error: string | null;
  tracks: {
    video: MediaStreamTrack | null;
    audio: MediaStreamTrack | null;
  };
}

// Presence Types
export interface PresenceData {
  userId: string;
  userName: string;
  userColor: string;
  organizationId: string;
  status: "online" | "idle" | "away" | "offline";
  cursor?: { x: number; y: number };
  selection?: { start: number; end: number };
  lastActivity: number;
  documentId?: string;
  threadId?: string;
}

// Offline Sync Types
export interface SyncQueueItem {
  id: string;
  type: "document" | "presence" | "notification" | "custom";
  operation: "create" | "update" | "delete";
  payload: any;
  timestamp: number;
  retries: number;
  maxRetries: number;
  priority: "high" | "normal" | "low";
  status: "pending" | "syncing" | "completed" | "failed";
  error?: string;
}

export interface OfflineSyncState {
  isInitialized: boolean;
  isOnline: boolean;
  isSyncing: boolean;
  pendingChanges: number;
  pendingSyncItems: number;
  lastSyncTime: number | null;
  syncError: string | null;
  lastSyncStatus: "idle" | "syncing" | "completed" | "failed";
}

// RAG/Knowledge Types
export interface KnowledgeSearchResult {
  id: string;
  kind: string;
  title: string;
  url: string;
  subtitle: string;
  score: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: KnowledgeSearchResult[];
  total: int;
  limit: int;
  provider: string;
  took_ms: number;
}

// API Response Types
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// WebSocket Message Types
export interface WSMessage {
  type: string;
  payload: any;
  requestId?: string;
}

// Collaboration Event Types
export type CollaborationEventType =
  | "document:created"
  | "document:updated"
  | "document:deleted"
  | "comment:created"
  | "comment:updated"
  | "comment:deleted"
  | "thread:created"
  | "thread:updated"
  | "thread:deleted"
  | "thread:resolved"
  | "thread:reopened"
  | "presence:join"
  | "presence:leave"
  | "presence:update"
  | "cursor:update"
  | "selection:update"
  | "typing:start"
  | "typing:stop";

export interface CollaborationEvent {
  type: CollaborationEventType;
  documentId: string;
  userId: string;
  payload: any;
  timestamp: number;
}

// Hook Return Types
export interface UseCRDTDocumentReturn {
  content: string | any[];
  version: number;
  clients: Map<string, any>;
  isConnected: boolean;
  connectionError: string | null;
  lastModified: number;
  sendOperation: (
    operation: Omit<CRDTOperation, "id" | "timestamp" | "clientId">,
  ) => void;
  sendAwareness: (awareness: Partial<AwarenessState>) => void;
  updateCursor: (position: { x: number; y: number }) => void;
  updateSelection: (selection: { start: number; end: number }) => void;
  updateStatus: (status: "online" | "idle" | "away" | "offline") => void;
  connect: () => void;
  disconnect: () => void;
}

export interface UseCallReturn {
  callId: string;
  callType: CallType;
  state: CallState;
  participants: CallParticipant[];
  localParticipant: CallParticipant | null;
  isVideoEnabled: boolean;
  isAudioEnabled: boolean;
  isScreenSharing: boolean;
  isRecording: boolean;
  connectionState: "connecting" | "connected" | "disconnected" | "reconnecting";
  livekitRoom: string | null;
  livekitToken: string | null;
  recordingId: string | null;
  initiateCall: (options: {
    callType: CallType;
    targetUsers: string[];
    settings?: Record<string, any>;
  }) => Promise<any>;
  acceptCall: (callId: string) => Promise<any>;
  rejectCall: (callId: string) => Promise<void>;
  endCall: () => Promise<void>;
  leaveCall: () => Promise<void>;
  toggleMute: () => void;
  toggleVideo: () => void;
  toggleScreenShare: () => void;
  toggleRecording: () => void;
  sendChatMessage: (content: string) => void;
  chatMessages: Array<{ sender: string; content: string; timestamp: Date }>;
}

export interface UseCommentsReturn {
  threads: CommentThread[];
  loading: boolean;
  error: string | null;
  createThread: (
    anchor: CommentThread["anchor"],
    initialComment: string,
  ) => Promise<CommentThread>;
  deleteThread: (threadId: string) => Promise<void>;
  resolveThread: (threadId: string) => Promise<void>;
  reopenThread: (threadId: string) => Promise<void>;
  assignThread: (threadId: string, userId: string) => Promise<void>;
  addLabel: (threadId: string, label: string) => Promise<void>;
  removeLabel: (threadId: string, label: string) => Promise<void>;
  addComment: (
    threadId: string,
    content: string,
    parentId?: string,
  ) => Promise<Comment>;
  updateComment: (
    threadId: string,
    commentId: string,
    content: string,
  ) => Promise<void>;
  deleteComment: (threadId: string, commentId: string) => Promise<void>;
  reactToComment: (
    threadId: string,
    commentId: string,
    emoji: string,
  ) => Promise<void>;
  removeReaction: (
    threadId: string,
    commentId: string,
    emoji: string,
  ) => Promise<void>;
  mentionUser: (
    threadId: string,
    commentId: string,
    userId: string,
  ) => Promise<void>;
  subscribe: () => void;
  unsubscribe: () => void;
}

export interface UseScreenShareReturn {
  isSharing: boolean;
  stream: MediaStream | null;
  error: string | null;
  startScreenShare: (
    options?: ScreenShareOptions,
  ) => Promise<MediaStream | null>;
  stopScreenShare: () => void;
  toggleScreenShare: (options?: ScreenShareOptions) => Promise<void>;
  replaceTrack: (track: MediaStreamTrack) => Promise<void>;
}
