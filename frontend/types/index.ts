/**
 * VCOS TypeScript API contracts â mirror of the backend OpenAPI schemas (Phase 1).
 */

import type { CompanyExperienceProfile } from "./company-experience";

export type { CompanyExperienceProfile } from "./company-experience";
export type { NavigationGroup } from "./company-experience";
export type { SuggestedProfileOut } from "./company-experience";
export type { AdaptiveModuleOut } from "./company-experience";
export type { AdaptiveNavigationGroupOut } from "./company-experience";
export type { CompanyBrainInsightsOut } from "./company-experience";
export type { DigitalTwinOverlayOut } from "./company-experience";
export type { RecommendedActionOut } from "./company-experience";
export type { AdaptiveExperienceOut } from "./company-experience";
export type { ProfileTransitionPreviewOut } from "./company-experience";
export type { ModuleRecommendationOut } from "./company-experience";
export type { MFAMethod } from "./company-experience";
export type { TOTPSetupResponse } from "./company-experience";
export type { IntegrationConnection } from "./company-experience";
export type { IntegrationConnectionCreate } from "./company-experience";
export type { IntegrationConnectionUpdate } from "./company-experience";
export type { IntegrationTestResult } from "./company-experience";
export type { IntegrationSyncResult } from "./company-experience";
export type { IntegrationKind } from "./company-experience";
export type { IntegrationAuthType } from "./company-experience";

export interface SecurityEvent {
  id: string;
  organization_id: string;
  user_id: string | null;
  event_type: string;
  severity: string;
  description: string;
  metadata_json: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  industry: string | null;
  description: string | null;
  logo_url: string | null;
  country: string | null;
  timezone: string;
  language: string;
  currency: string;
  status: string;
  domain: string | null;
  brand_primary_color: string;
  created_at: string;
  experience_profile?: CompanyExperienceProfile;
  employee_count?: number;
  organizational_depth?: number;
  organizational_unit_count?: number;
  legal_entity_count?: number;
  geographic_footprint_count?: number;
  governance_complexity?: string;
  workflow_complexity?: string;
}

export interface OrganizationSettings {
  allow_employee_self_registration: boolean;
  require_email_verification: boolean;
  default_theme: string;
  weekly_digest: boolean;
  announcement_enabled: boolean;
  retention_days_audit: number;
  retention_days_notifications: number;
}

export interface OrganizationStats {
  total_users: number;
  active_users: number;
  pending_invitations: number;
  roles_count: number;
  permissions_count: number;
  sessions_active: number;
  notifications_unread: number;
  audit_entries: number;
  created_at: string;
}

export interface RoleBrief {
  id: string;
  name: string;
  code: string;
  is_system: boolean;
  is_default: boolean;
}

export interface User {
  id: string;
  organization_id: string;
  email: string;
  username: string | null;
  full_name: string;
  status: string;
  role: string;
  timezone: string;
  language: string;
  avatar_url: string | null;
  phone: string | null;
  job_title: string | null;
  email_verified_at: string | null;
  last_login_at: string | null;
  created_at: string;
  roles: RoleBrief[];
  permissions: string[];
}

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  organization: Organization;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Session {
  id: string;
  device_name: string | null;
  device_type: string | null;
  browser: string | null;
  os: string | null;
  ip_address: string | null;
  created_at: string;
  last_activity_at: string | null;
  expires_at: string;
  is_current: boolean;
}

export interface Invitation {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  status: string;
  message: string | null;
  created_at: string;
  expires_at: string;
}

export interface InviteResult {
  invitation: Invitation;
  token: string | null;
  url: string | null;
}

export interface Permission {
  id: string;
  code: string;
  name: string;
  resource: string;
  action: string;
  description: string | null;
}

export interface Role {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_system: boolean;
  is_default: boolean;
  created_at: string;
  permissions: Permission[];
  user_count: number;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  priority: string;
  link: string | null;
  entity_type: string | null;
  entity_id: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationStats {
  total_unread: number;
  by_priority: Record<string, number>;
  by_type: Record<string, number>;
}

export interface AuditLog {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  severity: string;
  outcome: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface Workspace {
  id: string;
  user_id: string;
  daily_goal: string | null;
  onboarding_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceItem {
  id: string;
  kind: string;
  title: string;
  content: string | null;
  link: string | null;
  entity_type: string | null;
  entity_id: string | null;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceDashboard {
  workspace: Workspace;
  items: WorkspaceItem[];
  recent_items: WorkspaceItem[];
  pinned_items: WorkspaceItem[];
  notes_count: number;
  bookmarks_count: number;
}

export interface SearchResult {
  type: string;
  id: string;
  title: string;
  subtitle: string | null;
  url: string;
  snippet: string | null;
  score: number;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  took_ms: number;
}

export interface DashboardSummary {
  organization_name: string;
  organization_slug: string;
  current_user: {
    id: string;
    full_name: string;
    email: string;
    role: string;
    job_title: string | null;
    avatar_url: string | null;
  };
  total_users: number;
  active_users: number;
  unread_notifications: number;
  active_sessions: number;
  pending_invitations: number;
  roles_count: number;
  recent_activity: {
    id: string;
    action: string;
    actor_email: string | null;
    severity: string;
    created_at: string;
  }[];
  recent_notifications: {
    id: string;
    type: string;
    title: string;
    body: string | null;
    priority: string;
    is_read: boolean;
    created_at: string;
  }[];
  my_tasks_open_count: number;
  pending_decisions_count: number;
  pending_approvals_count: number;
  workspace: {
    id: string;
    daily_goal: string | null;
    onboarding_completed: boolean;
    items: {
      id: string;
      kind: string;
      title: string;
      pinned: boolean;
      created_at: string;
    }[];
  } | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Message {
  message: string;
  detail?: string | null;
}

export interface PlatformInfo {
  name: string;
  version: string;
  environment: string;
  api_version: string;
  ai_provider: string;
  features: { foundation: boolean; ai_foundation: boolean; redis: boolean };
}

// ---------------------------------------------------------------------------
// Phase 2 â People & Organization
// ---------------------------------------------------------------------------

export interface EmployeeSummary {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string | null;
  display_name: string | null;
  full_name: string;
  email: string;
  user_id: string | null;
  avatar_url: string | null;
  designation: string | null;
  department_id: string | null;
  department_name: string | null;
  team_id: string | null;
  team_name: string | null;
  manager_id: string | null;
  manager_name: string | null;
  location_id: string | null;
  location_name: string | null;
  employment_type: string;
  joining_date: string | null;
  status: string;
  timezone: string;
  expertise_score: number;
  profile_completion: number;
  availability_status: string | null;
  presence_status: string | null;
  is_online: boolean;
  top_skills: string[];
  is_favorite: boolean;
}

export interface EmployeeSkill {
  id: string;
  skill_id: string;
  name: string;
  category: string | null;
  level: number;
  years_experience: number;
  verified: boolean;
}

export interface Certification {
  id: string;
  name: string;
  issuer: string | null;
  credential_id: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  verified: boolean;
}

export interface Achievement {
  id: string;
  kind: string;
  title: string;
  description: string | null;
  achieved_on: string | null;
}

export interface Employee extends EmployeeSummary {
  user_id: string | null;
  phone: string | null;
  language: string | null;
  bio: string | null;
  emergency_contact: Record<string, unknown> | null;
  business_unit_id: string | null;
  business_unit_name: string | null;
  ai_summary: string | null;
  skills: EmployeeSkill[];
  certifications: Certification[];
  achievements: Achievement[];
  timeline_count: number;
  reports_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface TimelineEntry {
  id: string;
  kind: string;
  title: string;
  description: string | null;
  meta: Record<string, unknown> | null;
  occurred_at: string;
}

export interface Department {
  id: string;
  name: string;
  code: string;
  description: string | null;
  parent_id: string | null;
  parent_name: string | null;
  head_id: string | null;
  head_name: string | null;
  location_id: string | null;
  location_name: string | null;
  members_count: number;
  teams_count: number;
  children: { id: string; name: string }[];
}

export interface DepartmentStats {
  department_id: string;
  department_name: string;
  members: number;
  teams: number;
  avg_expertise: number;
  skills: { skill: string; count: number }[];
}

export interface TeamMember {
  id: string;
  employee_id: string;
  employee_name: string;
  designation: string | null;
  avatar_url: string | null;
  role: string | null;
  joined_at: string | null;
  is_primary: boolean;
}

export interface Team {
  id: string;
  name: string;
  code: string;
  description: string | null;
  department_id: string | null;
  department_name: string | null;
  lead_id: string | null;
  lead_name: string | null;
  members_count: number;
  members: TeamMember[];
}

export interface Location {
  id: string;
  name: string;
  code: string;
  city: string | null;
  country: string | null;
  address: string | null;
  is_office: boolean;
  timezone: string | null;
  employees_count: number;
}

export interface BusinessUnit {
  id: string;
  name: string;
  code: string;
  description: string | null;
  head_id: string | null;
  head_name: string | null;
  parent_id: string | null;
  employees_count: number;
}

export interface OrganizationStructure {
  departments: Department[];
  teams: Team[];
  locations: Location[];
  business_units: BusinessUnit[];
}

export interface OrgChartNode {
  id: string;
  employee_number: string;
  name: string;
  designation: string | null;
  department: string | null;
  team: string | null;
  avatar_url: string | null;
  is_online: boolean;
  children: OrgChartNode[];
}

export interface OrgChartResponse {
  root: OrgChartNode | null;
  roots: OrgChartNode[];
  total: number;
  max_depth: number;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: string;
  designation: string | null;
  meta: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface OrganizationGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Skill {
  id: string;
  name: string;
  category: string | null;
  description: string | null;
  employees_count: number;
}

export interface ExpertiseScore {
  id: string;
  employee_id: string;
  skill_id: string;
  skill_name: string;
  category: string | null;
  score: number;
  level: number;
  years_experience: number;
  factors: Record<string, unknown> | null;
  updated_at: string | null;
}

export interface Expert {
  employee_id: string;
  employee_number: string;
  name: string;
  designation: string | null;
  department: string | null;
  team: string | null;
  avatar_url: string | null;
  skill: string;
  score: number;
  level: number;
  years_experience: number;
  is_online: boolean;
}

export interface Successor {
  employee_id: string;
  employee_number: string;
  name: string;
  designation: string | null;
  department: string | null;
  avatar_url: string | null;
  score: number;
  reasons: string[];
}

export interface Mentor {
  employee_id: string;
  name: string;
  designation: string | null;
  skill: string;
  score: number;
  years_experience: number;
}

export interface SkillGap {
  skill: string;
  category: string | null;
  demand: number;
  supply: number;
  ratio: number;
}

export interface OrgIntelligence {
  total_employees: number;
  active_employees: number;
  departments: number;
  teams: number;
  locations: number;
  business_units: number;
  managers: number;
  avg_expertise: number;
  avg_profile_completion: number;
  online_now: number;
  on_leave: number;
  recent_joins: {
    employee_id: string;
    name: string;
    designation: string | null;
    employee_number: string;
    joining_date: string | null;
  }[];
  recent_transfers: {
    employee_id: string;
    title: string;
    description: string | null;
    occurred_at: string;
  }[];
  department_distribution: {
    department_id: string;
    name: string;
    count: number;
  }[];
  team_distribution: { team_id: string; name: string; count: number }[];
  location_distribution: { location_id: string; name: string; count: number }[];
  skill_distribution: { skill_id: string; name: string; count: number }[];
  growth_30d: number;
  growth_90d: number;
  reporting_depth: number;
  management_span: number;
  org_health: number;
}

export interface Presence {
  id: string;
  employee_id: string;
  is_online: boolean;
  status: string;
  last_active_at: string | null;
  working_hours: Record<string, unknown> | null;
  timezone: string | null;
  device: string | null;
  updated_at: string | null;
}

export interface Availability {
  id: string;
  employee_id: string;
  status: string;
  note: string | null;
  available_from: string | null;
  available_until: string | null;
  updated_at: string | null;
}

// ---------------------------------------------------------------------------
// Phase 3 â Work Execution Engine
// ---------------------------------------------------------------------------

export interface Project {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: string;
  priority: string;
  progress: number;
  health: string;
  owner_id: string | null;
  owner_name: string | null;
  department_id: string | null;
  department_name: string | null;
  team_id: string | null;
  team_name: string | null;
  roadmap_id: string | null;
  start_date: string | null;
  end_date: string | null;
  budget: number | null;
  tags: string[] | null;
  ai_summary: string | null;
  members_count: number;
  tasks_count: number;
  completed_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProjectMember {
  id: string;
  employee_id: string;
  name: string;
  designation: string | null;
  avatar_url: string | null;
  role: string | null;
  joined_at: string | null;
}

export interface ProjectStats {
  project_id: string;
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
  blocked_tasks: number;
  progress: number;
  milestones_total: number;
  milestones_completed: number;
  status_breakdown: Record<string, number>;
}

export interface ProjectHealth {
  project_id: string;
  health: number;
  status: string;
  signals: string[];
  progress: number;
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
  blocked_tasks: number;
  overdue_tasks: number;
  milestones_total: number;
  milestones_completed: number;
  overdue_milestones: number;
  risks: {
    id: string;
    title: string;
    risk_score: number;
    severity: string;
    status: string;
  }[];
}

export interface Roadmap {
  id: string;
  name: string;
  description: string | null;
  owner_id: string | null;
  owner_name: string | null;
  timeframe: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Epic {
  id: string;
  project_id: string | null;
  roadmap_id: string | null;
  name: string;
  description: string | null;
  status: string;
  priority: string;
  progress: number;
  tasks_count: number;
  start_date: string | null;
  end_date: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Milestone {
  id: string;
  project_id: string | null;
  roadmap_id: string | null;
  name: string;
  description: string | null;
  due_date: string | null;
  status: string;
  progress: number;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Sprint {
  id: string;
  project_id: string | null;
  name: string;
  goal: string | null;
  start_date: string | null;
  end_date: string | null;
  status: string;
  progress: number;
  tasks_count: number;
  completed_tasks: number;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Task {
  id: string;
  project_id: string | null;
  project_name: string | null;
  epic_id: string | null;
  milestone_id: string | null;
  sprint_id: string | null;
  parent_task_id: string | null;
  parent_title: string | null;
  decision_id: string | null;
  decision: TaskDecisionLineage | null;
  goal_id: string | null;
  goal_name: string | null;
  subtasks_count: number;
  subtasks_completed: number;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  assignee_id: string | null;
  assignee_name: string | null;
  assignee_avatar_url: string | null;
  reporter_id: string | null;
  reporter_name: string | null;
  estimate_hours: number | null;
  spent_hours: number;
  start_date: string | null;
  due_date: string | null;
  completed_at: string | null;
  progress: number;
  tags: string[] | null;
  ai_summary: string | null;
  dependencies:
    | {
        id: string;
        depends_on_task_id: string;
        depends_on_title: string;
        kind: string;
      }[]
    | null;
  blocking_tasks:
    { id: string; task_id: string; title: string; status: string }[] | null;
  blocked_by:
    | {
        id: string;
        task_id: string;
        title: string;
        status: string;
        kind: string;
      }[]
    | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskDecisionLineage {
  id: string;
  title: string;
  context: string | null;
  reason: string | null;
  status: string;
  decided_at: string | null;
  project_id: string | null;
}

export interface Dependency {
  id: string;
  task_id: string;
  depends_on_task_id: string;
  depends_on_title: string | null;
  kind: string;
  created_at: string | null;
}

export interface TaskComment {
  id: string;
  task_id: string;
  author_id?: string;
  author_name?: string;
  body: string;
  mentions?: string[];
  created_at?: string;
}

export interface TaskAttachment {
  id: string;
  task_id: string;
  filename: string;
  url: string;
  size_bytes: number;
  kind?: string;
  uploaded_by?: string;
  uploaded_by_name?: string;
  created_at?: string;
}

export interface TaskActivityEntry {
  id: string;
  action: string;
  actor_id?: string;
  actor_email?: string;
  details?: Record<string, unknown> | null;
  created_at?: string;
}

export interface Goal {
  id: string;
  parent_goal_id: string | null;
  parent_name: string | null;
  name: string;
  description: string | null;
  scope: string;
  owner_id: string | null;
  owner_name: string | null;
  department_id: string | null;
  team_id: string | null;
  project_id: string | null;
  status: string;
  progress: number;
  priority: string;
  start_date: string | null;
  end_date: string | null;
  key_results_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KeyResult {
  id: string;
  goal_id: string;
  title: string;
  metric: string | null;
  unit: string | null;
  target: number | null;
  current: number | null;
  owner_id: string | null;
  owner_name: string | null;
  status: string;
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
  "host" | "co_host" | "presenter" | "participant" | "guest" | "observer";

export type ParticipantStatus =
  "invited" | "pending" | "joining" | "joined" | "left" | "reconnecting";

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

// ---------------------------------------------------------------- Phase 6: live collaboration

export interface MeetingChatMessage {
  id: string;
  meeting_id: string;
  session_id: string | null;
  employee_id: string | null;
  sender_name: string | null;
  sender_designation: string | null;
  avatar_url: string | null;
  content: string;
  kind: string;
  reply_to: string | null;
  created_at: string | null;
}

export interface MeetingWhiteboard {
  id: string;
  meeting_id: string;
  session_id: string | null;
  content: Record<string, unknown>;
  version: number;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface MeetingCaption {
  id: string;
  meeting_id: string;
  session_id: string | null;
  employee_id: string | null;
  speaker_name: string | null;
  language: string;
  text: string;
  translated_text: string | null;
  translation_language: string | null;
  start_ms: number;
  end_ms: number;
  created_at: string | null;
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

export interface MeetingRecording {
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

export interface LiveServerEvent {
  type: string;
  ts: number;
  data: Record<string, unknown>;
}

export interface CalendarEvent {
  id: string;
  title: string;
  description: string | null;
  event_type: string;
  start_at: string | null;
  end_at: string | null;
  all_day: boolean;
  location: string | null;
  calendar_scope: string;
  department_id: string | null;
  team_id: string | null;
  project_id: string | null;
  milestone_id: string | null;
  created_by: string | null;
  creator_name: string | null;
  attendee_ids: string[] | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface CalendarFeedItem {
  id: string;
  source: "event" | "meeting" | "task" | "leave" | "holiday";
  title: string;
  start_at: string | null;
  end_at: string | null;
  all_day: boolean;
  due_date: string | null;
  status: string | null;
  event_type: string | null;
  scope: string | null;
}

export interface TeamLoadMember {
  employee_id: string;
  full_name: string;
  utilization: number;
  allocated_hours: number;
  capacity_hours: number;
  is_overloaded: boolean;
}

export interface TeamLoadSummary {
  team_id: string;
  team_name: string;
  member_count: number;
  avg_utilization: number;
  overloaded_count: number;
  overloaded_employees: TeamLoadMember[];
}

export interface Approval {
  id: string;
  approval_type: string;
  title: string;
  description: string | null;
  requester_id: string | null;
  requester_name: string | null;
  approver_id: string | null;
  approver_name: string | null;
  status: string;
  priority: string;
  due_at: string | null;
  decided_at: string | null;
  decision_note: string | null;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Risk {
  id: string;
  project_id: string | null;
  project_name: string | null;
  title: string;
  description: string | null;
  status: string;
  probability: number;
  impact: number;
  risk_score: number;
  severity: string | null;
  owner_id: string | null;
  owner_name: string | null;
  mitigation: string | null;
  due_at: string | null;
  detected_from: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GovernanceScope {
  id: string;
  name: string;
  scope_type: string;
  parent_id: string | null;
  entity_id: string | null;
  depth: number;
  created_at: string | null;
}

export interface GovernanceAssignment {
  id: string;
  user_id: string;
  role_id: string;
  scope_id: string | null;
  created_at: string | null;
}

export interface GovernanceDelegation {
  id: string;
  granted_by: string | null;
  granted_to_user: string;
  permission_code: string;
  resource_type: string | null;
  resource_id: string | null;
  reason: string | null;
  starts_at: string | null;
  expires_at: string | null;
  status: string;
  created_at: string | null;
}

export interface ApprovalPolicy {
  id: string;
  name: string;
  approval_type: string;
  description: string | null;
  required_permission: string;
  scope_id: string | null;
  self_approval_allowed: boolean;
  is_active: boolean;
  created_at: string | null;
}

export interface EffectivePermissions {
  user_id: string;
  scope_id: string | null;
  permissions: string[];
  has_permission: Record<string, boolean>;
}

export interface Workload {
  employee_id: string;
  period_start: string;
  period_end: string;
  capacity_hours: number;
  allocated_hours: number;
  meeting_hours: number;
  utilization: number;
  active_tasks: number;
  is_overloaded: boolean;
}

export interface MyWork {
  employee_id: string;
  tasks: {
    total: number;
    completed: number;
    overdue: number;
    blocked: number;
    in_progress: number;
    estimate_hours: number;
  };
  workload: Workload;
  upcoming_meetings: number;
  goals: { id: string; name: string; status: string; progress: number }[];
  today_tasks: {
    id: string;
    title: string;
    status: string;
    due_date: string | null;
  }[];
}

export interface OrganizationLoad {
  employees_tracked: number;
  overloaded: number;
  underutilized: number;
  avg_utilization: number;
  overloaded_employees: string[];
}

export interface ExecutiveDashboard {
  projects_total: number;
  projects_active: number;
  projects_completed: number;
  avg_project_health: number;
  project_status: string;
  tasks_total: number;
  tasks_completed: number;
  tasks_blocked: number;
  tasks_completion_rate: number;
  meetings_last_7d: number;
  overloaded_employees: number;
  risks_open: number;
  high_risks: number;
  goals_total: number;
  goals_completed: number;
  goals_completion_rate: number;
  avg_progress: number;
}

// ---------------------------------------------------------------------------
// Phase 4 â Knowledge Operating System
// ---------------------------------------------------------------------------

export interface KnowledgeBase {
  id: string;
  kind: string;
  url: string;
  title: string;
  slug: string;
  description: string | null;
  content: string | null;
  summary: string | null;
  ai_summary: string | null;
  keywords: string | null;
  status: string;
  tags: string[];
  version: number;
  view_count: number;
  created_at: string;
  updated_at: string;
}

export interface Document extends KnowledgeBase {
  category: string | null;
  author_id: string | null;
  author_name: string | null;
  owner_id: string | null;
  owner_name: string | null;
  project_id: string | null;
  project_name: string | null;
  department_id: string | null;
  team_id: string | null;
  visibility: string;
  published_at: string | null;
}

export interface WikiPage extends KnowledgeBase {
  space: string;
  category: string | null;
  author_id: string | null;
  author_name: string | null;
  editor_id: string | null;
  parent_id: string | null;
  project_id: string | null;
  project_name: string | null;
  department_id: string | null;
  team_id: string | null;
  child_count: number;
  published_at: string | null;
}

export interface Policy extends KnowledgeBase {
  category: string;
  owner_id: string | null;
  owner_name: string | null;
  approver_id: string | null;
  approver_name: string | null;
  effective_date: string | null;
  review_date: string | null;
  review_overdue: boolean;
  approval_note: string | null;
  published_at: string | null;
}

export interface SOPStep {
  id: string;
  sop_id: string;
  title: string;
  instruction: string | null;
  is_checklist: boolean;
  sort_order: number;
}

export interface SOP extends KnowledgeBase {
  category: string | null;
  owner_id: string | null;
  owner_name: string | null;
  department_id: string | null;
  team_id: string | null;
  steps: SOPStep[];
  published_at: string | null;
}

export interface Template extends KnowledgeBase {
  kind_name: string;
  category: string | null;
  owner_id: string | null;
  owner_name: string | null;
  usage_count: number;
  published_at: string | null;
}

export interface DecisionOption {
  id: string;
  decision_id: string;
  title: string;
  description: string | null;
  pros: string | null;
  cons: string | null;
  chosen: boolean;
  chosen_reason: string | null;
  sort_order: number;
}

export interface DecisionParticipant {
  id: string;
  decision_id: string;
  employee_id: string;
  employee_name: string | null;
  role: string;
}

export interface FollowUpAction {
  text: string;
  owner_id: string | null;
  owner_name: string | null;
  project_id: string | null;
  goal_id: string | null;
  due_date: string | null;
  status: "pending" | "in_progress" | "completed" | "skipped" | string;
  task_id: string | null;
}

export interface Decision extends KnowledgeBase {
  context: string | null;
  decision_maker_id: string | null;
  decision_maker_name: string | null;
  decision_date: string | null;
  impact: string | null;
  business_impact: string | null;
  follow_up_actions: FollowUpAction[] | null;
  future_review_date: string | null;
  lessons_learned: string | null;
  project_id: string | null;
  project_name: string | null;
  goal_id: string | null;
  goal_name: string | null;
  meeting_id: string | null;
  department_id: string | null;
  decided_at: string | null;
  options: DecisionOption[];
  participants: DecisionParticipant[];
  tasks: Task[];
}

export interface KnowledgeSearchResult {
  id: string;
  kind: string;
  title: string;
  url: string;
  subtitle: string | null;
  snippet: string | null;
  score: number;
  matched_keywords: string[];
  metadata: Record<string, unknown>;
}

export interface KnowledgeSearchResponse {
  query: string;
  mode: string;
  results: KnowledgeSearchResult[];
  total: number;
  took_ms: number;
}

export interface KnowledgeGraphNode {
  id: string;
  label: string;
  kind: string;
  status: string | null;
  meta: Record<string, unknown>;
}

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface KnowledgeGraph {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

export interface KnowledgeVersion {
  id: string;
  entity_type: string;
  entity_id: string;
  version: number;
  title: string;
  content: string | null;
  summary: string | null;
  editor_id: string | null;
  editor_name: string | null;
  change_note: string | null;
  created_at: string;
}

export interface KnowledgeComment {
  id: string;
  entity_type: string;
  entity_id: string;
  author_id: string;
  author_name: string | null;
  content: string;
  parent_id: string | null;
  resolved: boolean;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeWatcher {
  id: string;
  entity_type: string;
  entity_id: string;
  user_id: string;
  user_name: string | null;
  created_at: string;
}

export interface KnowledgeFavorite {
  id: string;
  entity_type: string;
  entity_id: string;
  user_id: string;
  created_at: string;
}

export interface KnowledgePresence {
  entity_type: string;
  entity_id: string;
  user_id: string;
  user_name: string | null;
  last_active_at: string;
}

export interface KnowledgeRelation {
  id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  relation_type: string;
  target_title: string | null;
  target_url: string | null;
  created_at: string;
}

export interface KnowledgeCategory {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  color: string | null;
}

export interface KnowledgeTag {
  id: string;
  name: string;
  slug: string;
}

export interface KnowledgeRecommendation {
  id: string;
  kind: string;
  title: string;
  url: string;
  reason: string;
  score: number;
  status: string | null;
}

export interface KnowledgeExpert {
  employee_id: string;
  name: string;
  documents_count: number;
  expertise: string;
}

export interface KnowledgeRecentItem {
  id: string;
  kind: string;
  title: string;
  url: string;
  status: string;
  viewed_at: string;
}

export interface KnowledgeAnalytics {
  totals: Record<string, number>;
  total_items: number;
  total_relations: number;
  avg_quality_score: number;
  growth_30d: Record<string, number>;
  growth_series: { date: string; count: number }[];
  top_viewed: {
    id: string;
    kind: string;
    title: string;
    url: string;
    views: number;
  }[];
  top_contributors: { employee_id: string; name: string; count: number }[];
  category_coverage: Record<string, unknown>[];
  department_health: Record<string, unknown>[];
  outdated: {
    id: string;
    type: string;
    title: string;
    status: string;
    url: string;
    updated_at: string | null;
  }[];
  review_backlog: {
    id: string;
    kind: string;
    title: string;
    url: string;
    status: string;
  }[];
  quality_distribution: Record<string, number>;
  expert_distribution: Record<string, unknown>[];
  search_trends: Record<string, unknown>[];
  duplicates: {
    entity_type: string;
    entity_id: string;
    duplicate_of: string;
  }[];
  coverage: { projects_with_knowledge: number };
  quality_lowest: {
    id: string;
    entity_type: string;
    entity_id: string;
    score: number;
    issues: string[];
  }[];
}

export interface WikiTreeNode {
  id: string;
  title: string;
  space: string;
  status: string;
  url: string;
  parent_id: string | null;
  child_count: number;
  children: WikiTreeNode[];
}

// ---------------------------------------------------------------------------
// Phase 5 â Communication & Community
// ---------------------------------------------------------------------------

export interface Community {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  type: string;
  visibility: "public" | "private" | "hidden";
  icon: string | null;
  banner: string | null;
  owner_id: string;
  member_count: number;
  post_count: number;
  is_featured: boolean;
  is_archived: boolean;
  is_member: boolean;
  my_role: "owner" | "moderator" | "member" | null;
  created_at: string;
  updated_at: string;
}

export interface CommunityMember {
  id: string;
  community_id: string;
  employee_id: string;
  employee_name: string | null;
  role: string;
  notifications_enabled: boolean;
  joined_at: string;
}

export interface Post {
  id: string;
  community_id: string;
  community_name: string;
  author_id: string;
  author_name: string;
  title: string | null;
  content: string | null;
  attachments: unknown[] | null;
  visibility: string;
  status: string;
  pinned: boolean;
  scheduled_at: string | null;
  edited_at: string | null;
  comment_count: number;
  reaction_count: number;
  bookmark_count: number;
  share_count: number;
  is_bookmarked: boolean;
  my_reaction: string | null;
  created_at: string;
  updated_at: string;
}

export interface PostComment {
  id: string;
  post_id: string;
  parent_id: string | null;
  author_id: string;
  author_name: string;
  content: string;
  is_resolution: boolean;
  edited: boolean;
  edited_at: string | null;
  reaction_count: number;
  my_reaction: string | null;
  created_at: string;
  updated_at: string;
}

export interface Announcement {
  id: string;
  title: string;
  body: string | null;
  type: string;
  priority: "low" | "normal" | "high" | "urgent";
  status: string;
  author_id: string;
  author_name: string;
  department_id: string | null;
  department_name: string | null;
  team_id: string | null;
  starts_at: string | null;
  ends_at: string | null;
  pinned: boolean;
  acknowledge_required: boolean;
  attachments: unknown[] | null;
  read_count: number;
  acknowledged_count: number;
  read_by_me: boolean;
  acknowledged_by_me: boolean;
  created_at: string;
  updated_at: string;
}

export interface AnnouncementReceipt {
  id: string;
  announcement_id: string;
  employee_id: string;
  employee_name: string | null;
  read_at: string | null;
  acknowledged_at: string | null;
}

export interface ForumThread {
  id: string;
  category: string;
  title: string;
  content: string | null;
  author_id: string;
  author_name: string;
  status: string;
  tags: string[];
  vote_count: number;
  reply_count: number;
  view_count: number;
  is_pinned: boolean;
  accepted_reply_id: string | null;
  is_resolved: boolean;
  my_vote: number | null;
  created_at: string;
  updated_at: string;
}

export interface ForumReply {
  id: string;
  thread_id: string;
  parent_id: string | null;
  author_id: string;
  author_name: string;
  content: string;
  is_accepted: boolean;
  vote_count: number;
  edited: boolean;
  my_vote: number | null;
  created_at: string;
  updated_at: string;
}

export interface Recognition {
  id: string;
  giver_id: string;
  giver_name: string;
  recipient_id: string;
  recipient_name: string;
  category: string;
  message: string | null;
  badge_code: string | null;
  public: boolean;
  created_at: string;
}

export interface Badge {
  id: string;
  code: string;
  name: string;
  description: string | null;
  icon: string;
  category: string;
}

export interface EmployeeBadge {
  id: string;
  badge_id: string;
  badge_code: string;
  badge_name: string;
  badge_icon: string;
  badge_category: string;
  employee_id: string;
  awarded_by: string | null;
  reason: string | null;
  created_at: string;
}

export interface Idea {
  id: string;
  author_id: string;
  author_name: string;
  title: string;
  description: string | null;
  problem: string | null;
  solution: string | null;
  impact: string | null;
  status: string;
  vote_count: number;
  comment_count: number;
  tags: string[];
  project_id: string | null;
  project_name: string | null;
  duplicates_of: string | null;
  ai_insight: string | null;
  voted: boolean;
  submitted_at: string;
  created_at: string;
  updated_at: string;
}

export interface PollOption {
  id: string;
  poll_id: string;
  text: string;
  sort_order: number;
  vote_count: number;
}

export interface Poll {
  id: string;
  title: string;
  question: string | null;
  description: string | null;
  community_id: string | null;
  community_name: string | null;
  created_by: string;
  creator_name: string;
  anonymous: boolean;
  multiple_choice: boolean;
  status: string;
  ends_at: string | null;
  vote_count: number;
  participant_count: number;
  options: PollOption[];
  voted: boolean;
  my_choices: string[];
  created_at: string;
  updated_at: string;
}

export interface PollResult {
  poll_id: string;
  vote_count: number;
  options: {
    option_id: string;
    text: string;
    vote_count: number;
    percentage: number;
  }[];
}

export interface CommunityEvent {
  id: string;
  title: string;
  description: string | null;
  type: string;
  community_id: string | null;
  community_name: string | null;
  created_by: string;
  creator_name: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  virtual_url: string | null;
  capacity: number;
  status: string;
  registration_deadline: string | null;
  team_based: boolean;
  registration_count: number;
  registered: boolean;
  my_registration: {
    id: string;
    team_name: string | null;
    role: string;
    status: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface EventRegistration {
  id: string;
  event_id: string;
  employee_id: string;
  employee_name: string | null;
  team_name: string | null;
  role: string;
  status: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  type: string;
  title: string | null;
  channel_kind: string | null;
  channel_key: string | null;
  community_id: string | null;
  created_by: string;
  is_archived: boolean;
  last_message_at: string | null;
  message_count: number;
  member_count: number;
  unread_count: number;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMember {
  employee_id: string;
  employee_name: string | null;
  role: string;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_name: string;
  content: string | null;
  reply_to: string | null;
  edited: boolean;
  deleted: boolean;
  deleted_at: string | null;
  attachments: unknown[] | null;
  mentions: string[];
  reaction_count: number;
  reactions: { emoji: string; count: number }[];
  read_by: string[];
  created_at: string;
  updated_at: string;
}

export interface CommunityAnalytics {
  overview: {
    communities: number;
    members: number;
    active_communities: number;
    posts: number;
    comments: number;
    reactions: number;
    forum_threads: number;
    forum_replies: number;
    announcements: number;
    recognitions: number;
    ideas: number;
    polls: number;
    events: number;
  };
  top_communities: {
    community_id: string;
    name: string;
    type: string;
    member_count: number;
    post_count: number;
  }[];
  top_contributors: { employee_id: string; name: string; score: number }[];
  activity_trend: {
    date: string;
    posts: number;
    comments: number;
    reactions: number;
    threads: number;
    replies: number;
    announcements: number;
    recognitions: number;
    polls: number;
  }[];
}

export const POST_REACTIONS = [
  "helpful",
  "congrats",
  "great_idea",
  "excellent",
  "appreciate",
  "support",
  "love",
  "insightful",
] as const;

// Slice 4D.1 - Canonical Company Intelligence & Evidence Layer

export interface BrainAnswerRequest {
  question: string;
  entity_type?: string | null;
  entity_id?: string | null;
  conversation_id?: string | null;
}

export interface BrainEvidenceRef {
  type: string;
  id: string;
  title: string;
  url: string;
}

export interface BrainClaim {
  claim: string;
  evidence: BrainEvidenceRef[];
  confidence: number;
  auth_scope: { scope_ids: string[] };
  timestamp: string;
}

export interface BrainAnswer {
  question: string;
  claims: BrainClaim[];
  scope_ids: string[];
  answered_at: string;
  // Slice 4D.6 - unified company brain additions
  summary: string;
  confidence: number;
  related_entities: BrainRelatedEntity[];
  patterns: BrainAnswerSectionPattern[];
  memories: BrainAnswerSectionMemory[];
  insights: BrainAnswerSectionInsight[];
  knowledge: BrainAnswerSectionKnowledge[];
  sources_consulted: string[];
  scope: { org_wide: boolean };
  generated_at: string;
  metrics: {
    brain_query: string;
    brain_query_duration_ms: number;
    sources_consulted: number;
    evidence_count: number;
    answer_claim_count: number;
    governance_filtered_count: number;
    // Slice 4D.7 - unified brain surface additions
    timeline_entries?: number;
    reasoning_chain_steps?: number;
    recommended_next_questions?: number;
  };
  // Slice 4D.7 - unified company brain surface additions
  conversation?: BrainConversationRef;
  persona?: BrainPersona;
  timeline?: BrainTimelineEntry[];
  recommended_next_questions?: string[];
  reasoning_chain?: BrainReasoningChainStep[];
  related_patterns?: BrainRelatedProjection[];
  related_memories?: BrainRelatedProjection[];
  related_insights?: BrainRelatedProjection[];
  what_changed?: BrainWhatChanged;
}

export interface BrainConversationRef {
  id: string;
  turn: number;
}

export interface BrainPersona {
  org_wide: boolean;
  visible_project_count: number;
  visible_scope_count: number;
}

export interface BrainTimelineEntry {
  kind: "memory" | "pattern" | "insight" | "project_timeline";
  id: string;
  title: string;
  url: string;
  occurred_at?: string | null;
  confidence?: number | null;
}

export interface BrainReasoningChainStep {
  step: number;
  label: string;
  claim: string;
  evidence: BrainEvidenceRef[];
  confidence: number;
}

export interface BrainRelatedProjection {
  id: string;
  title: string;
  confidence: number;
  url: string;
  pattern_type?: string | null;
  memory_category?: string | null;
  insight_type?: string | null;
}

export interface BrainWhatChangedCategory {
  category: string;
  count: number;
  items?: {
    type: string;
    id: string;
    title: string;
    url: string;
    timestamp?: string | null;
  }[];
}

export interface BrainWhatChanged {
  since: string;
  days: number;
  org_wide: boolean;
  categories: BrainWhatChangedCategory[];
}

export interface BrainConversation {
  id: string;
  organization_id: string;
  user_id: string;
  turn_count: number;
  last_anchor_type?: string | null;
  last_anchor_id?: string | null;
  last_anchor_title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  turns?: BrainConversationTurn[];
}

export interface BrainConversationTurn {
  id: string;
  conversation_id: string;
  question: string;
  summary?: string | null;
  anchor_type?: string | null;
  anchor_id?: string | null;
  anchor_title?: string | null;
  created_at?: string | null;
}

export interface BrainTimelineResponse {
  timeline: BrainTimelineEntry[];
  count: number;
  limit: number;
  entity: { type: string; id: string; title?: string | null } | null;
  scope: { org_wide: boolean };
  generated_at: string;
  metrics: {
    brain_query: string;
    timeline_entries: number;
    sources_consulted: number;
  };
}

export interface BrainRelatedEntity {
  type: string;
  id: string;
  title: string;
  relation?: string;
  url?: string;
}

export interface BrainAnswerSectionPattern {
  id: string;
  title: string;
  pattern_type: string;
  family?: string | null;
  occurrence_count?: number;
  confidence: number;
  status?: string | null;
  last_seen?: string | null;
  url: string;
}

export interface BrainAnswerSectionInsight {
  id: string;
  title: string;
  insight_type?: string | null;
  severity?: string | null;
  confidence: number;
  status?: string | null;
  last_observed_at?: string | null;
  url: string;
}

export interface BrainAnswerSectionMemory {
  id: string;
  title: string;
  memory_category?: string | null;
  fact_kind?: string | null;
  confidence: number;
  occurred_at?: string | null;
  url: string;
}

export interface BrainAnswerSectionKnowledge {
  source_type?: string | null;
  id: string;
  title: string;
  snippet?: string | null;
  score: number;
  url: string;
}

export interface BrainEvidenceLink {
  type: "pattern" | "insight" | "memory" | "knowledge";
  id: string;
  title: string;
  relationship: string;
  url: string;
  timestamp?: string | null;
}

export interface BrainEvidenceResponse {
  source: BrainRelatedEntity & Record<string, unknown>;
  evidence: BrainEvidenceLink[];
  related_entities: BrainRelatedEntity[];
  links: {
    patterns: number;
    insights: number;
    memories: number;
    knowledge: number;
  };
  limit: number;
  generated_at: string;
}

export interface BrainRelatedResponse {
  source: BrainRelatedEntity & Record<string, unknown>;
  related: BrainRelatedEntity[];
  limit: number;
  truncated: boolean;
  generated_at: string;
}

export interface BrainAttentionItem {
  source: "insight" | "pattern" | "memory";
  id: string;
  title: string;
  detail?: string | null;
  confidence: number;
  url: string;
}

export interface BrainUnifiedOverview {
  attention: BrainAttentionItem[];
  recent_intelligence: {
    insights: {
      count: number;
      latest: Record<string, unknown>[];
      truncated: boolean;
    };
    patterns: {
      count: number;
      latest: Record<string, unknown>[];
      truncated: boolean;
    };
    memories: {
      count: number;
      latest: Record<string, unknown>[];
      truncated: boolean;
    };
  };
  scope: { org_wide: boolean };
  generated_at: string;
  metrics?: {
    brain_query?: string;
    brain_query_duration_ms?: number;
    sources_consulted?: number;
  };
}

// Slice 4D.2 - Semantic Company Knowledge Intelligence

export interface BrainKnowledgeSearchRequest {
  question: string;
  kinds?: string[] | null;
  limit?: number | null;
}

export interface BrainKnowledgeSearchResult {
  source_type: string;
  source_id: string;
  title: string;
  snippet: string;
  chunk_index: number;
  url: string;
  status: string | null;
  project_id: string | null;
  category: string | null;
  scope: string;
  provider: string;
  semantic_score: number;
  lexical_score: number;
  retrieval_score: number;
  updated_at: string | null;
  indexed_at: string | null;
}

export interface BrainKnowledgeSearchResponse {
  query: string;
  results: BrainKnowledgeSearchResult[];
  total: number;
  limit: number;
  provider: string | null;
  truncated: boolean;
}

// Slice 4D.3 - Organizational Memory Automation

export interface BrainMemoryEvidenceItem {
  type: string;
  id: string;
  relationship: string;
  title?: string;
  url?: string;
  occurred_at?: string | null;
  resolved?: boolean;
}

export interface BrainMemory {
  id: string;
  memory_type: string;
  memory_category: string;
  domain: string | null;
  title: string;
  summary: string | null;
  content: string | null;
  lesson: string | null;
  outcome: string | null;
  outcome_type: string | null;
  confidence: number;
  fact_kind: string | null;
  importance: string;
  entity_type: string | null;
  entity_id: string | null;
  occurred_at: string | null;
  auth_scope: string;
  auth_project_id: string | null;
  status: string;
  supersedes_id: string | null;
  source_event_ids: string[];
  related_memory_ids: string[];
  evidence: BrainMemoryEvidenceItem[];
  context: Record<string, unknown>;
  source_event: string | null;
  tags: string[];
  created_at: string | null;
}

export interface BrainMemoryFeedResponse {
  memories: BrainMemory[];
}

export interface BrainMemorySearchResponse {
  memories: BrainMemory[];
  matched: number;
}

export interface BrainMemoryTimelineEpisode extends BrainMemory {
  episode_events: string[];
}

export interface BrainMemoryTimelineResponse {
  episodes: BrainMemoryTimelineEpisode[];
}

export interface BrainMemoryEvidenceResponse {
  memory: BrainMemory;
  evidence: BrainMemoryEvidenceItem[];
}

export interface BrainMemoryRelatedResponse {
  memory: BrainMemory;
  related: BrainMemory[];
}

export interface BrainMemoryOutcomeRequest {
  entity_type?: string | null;
  entity_id?: string | null;
  outcome_type: "positive" | "negative" | "partial" | "unresolved";
  outcome: string | null;
}

// Slice 4D.4 - Universal Organizational Pattern Intelligence

export type PatternFamily =
  | "execution"
  | "decision"
  | "governance"
  | "communication"
  | "knowledge"
  | "organization";

export type PatternLifecycle =
  | "candidate"
  | "emerging"
  | "confirmed"
  | "persistent"
  | "fading"
  | "resolved"
  | "open"
  | "acknowledged"
  | "dismissed";

export interface BrainPattern {
  id: string;
  pattern_type: string;
  pattern_key: string;
  family: PatternFamily;
  title: string;
  description: string | null;
  detail: string | null;
  status: PatternLifecycle;
  count: number;
  occurrence_count: number;
  confidence: number;
  confidence_label: string;
  first_seen: string | null;
  last_seen: string | null;
  time_window_days: number;
  scope_id: string | null;
  scope_type: string;
  auth_project_id: string | null;
  entities: Array<{ type: string; id: string; title?: string }>;
  supporting_memory_ids: string[];
  supporting_event_ids: string[];
  supporting_relationships: Array<Record<string, unknown>>;
  trend: string;
  avg_interval_days: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BrainPatternEvidenceItem {
  type: string;
  id: string;
  title?: string;
  relationship?: string;
  occurred_at?: string | null;
}

export interface BrainPatternsListResponse {
  patterns: BrainPattern[];
  limit: number;
  truncated: boolean;
  org_wide: boolean;
}

export interface BrainPatternEvidenceResponse {
  pattern_id: string;
  pattern_type: string;
  evidence: BrainPatternEvidenceItem[];
  supporting_memories: Array<{
    id: string;
    title: string;
    memory_category: string | null;
    fact_kind: string | null;
    confidence: number;
    url: string;
  }>;
  relationships: Array<Record<string, unknown>>;
  entities: Array<{ type: string; id: string; title?: string }>;
  source_events: string[];
}

export interface BrainPatternHistoryResponse {
  pattern_id: string;
  history: Array<{
    event_id: string;
    event_name: string;
    occurred_at: string | null;
  }>;
  first_seen: string | null;
  last_seen: string | null;
  occurrence_count: number;
}

export interface BrainPatternRelatedResponse {
  pattern_id: string;
  related: Array<BrainPattern & { relation: string }>;
}

export type InsightType =
  | "execution_bottleneck"
  | "decision_bottleneck"
  | "ownership_ambiguity"
  | "knowledge_gap"
  | "communication_breakdown"
  | "organizational_bottleneck"
  | "governance_bottleneck"
  | "repeated_organizational_issue"
  | "cross_domain_risk";

export type InsightSeverity = "info" | "warning" | "critical";
export type InsightStatus = "active" | "faded" | "resolved";

export interface BrainInsightEvidenceItem {
  type: string;
  id: string;
  title?: string;
  relationship?: string;
  occurred_at?: string | null;
  meta?: Record<string, unknown>;
}

export interface BrainInsight {
  id: string;
  insight_type: InsightType;
  key?: string | null;
  domain: string;
  severity: InsightSeverity;
  title: string;
  claim?: string | null;
  summary?: string | null;
  confidence: number;
  confidence_components: {
    occurrence_strength?: number;
    evidence_completeness?: number;
    pattern_confidence?: number;
    memory_corroboration?: number;
    recency?: number;
    weights?: Record<string, number>;
  };
  evidence: BrainInsightEvidenceItem[];
  relationships: Array<Record<string, unknown>>;
  supporting_pattern_ids: string[];
  supporting_memory_ids: string[];
  scope_type: string;
  scope_id?: string | null;
  auth_project_id?: string | null;
  status: InsightStatus;
  affected_entities: Array<{ type: string; id: string; title?: string }>;
  first_observed_at?: string | null;
  last_observed_at?: string | null;
}

export interface BrainInsightsListResponse {
  insights: BrainInsight[];
  limit: number;
  truncated: boolean;
  org_wide: boolean;
}

export interface BrainInsightEvidenceResponse {
  insight_id: string;
  insight_type: string;
  evidence: BrainInsightEvidenceItem[];
  supporting_pattern_ids: string[];
  supporting_memory_ids: string[];
}

export interface BrainInsightHistoryResponse {
  insight_id: string;
  history: Array<{
    event_id: string;
    event_name: string;
    relationship: string;
    occurred_at?: string | null;
  }>;
  first_observed_at?: string | null;
  last_observed_at?: string | null;
  status: InsightStatus;
}

export interface BrainInsightRelatedResponse {
  insight_id: string;
  related: Array<BrainInsight & { relation: string }>;
}

export interface BrainGraphRelationshipNode {
  type: string;
  id: string;
}

export interface BrainGraphRelationshipEdge {
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  relation: string;
}

export interface BrainGraphTraversal {
  nodes: BrainGraphRelationshipNode[];
  edges: BrainGraphRelationshipEdge[];
  truncated: boolean;
  limits: { max_depth: number; max_nodes: number; max_edges: number };
}

// ---------------------------------------------------------------------------
// Slice 4E.5 — knowledge intelligence operating layer (knowledge-to-action)
// ---------------------------------------------------------------------------

export interface KnowledgeIntelInsight {
  id: string;
  kind: string;
  title: string;
  summary: string;
  severity: string;
  confidence: number;
  impact: string | null;
  urgency: string | null;
  priority_score: number;
  status: string;
  topic_id: string | null;
  topic_name: string | null;
  created_at: string;
  updated_at: string;
  evidence_count: number;
  claim_ids: string[];
}

export interface KnowledgeIntelInsightsResponse {
  total: number;
  kinds: string[];
  by_kind: Record<string, number>;
  scope: "org" | "project";
  insights: KnowledgeIntelInsight[];
}

export interface KnowledgeInsightLineageClaim {
  id: string;
  statement: string;
  status: string;
  confidence: number;
  authority_level: number;
  valid_from: string;
  source_type: string;
  source_id: string;
}

export interface KnowledgeInsightDetailResponse extends KnowledgeIntelInsight {
  lineage: {
    claims: KnowledgeInsightLineageClaim[];
    entities: Array<Record<string, unknown>>;
    source_event: string | null;
  };
  audit: Array<{
    action: string;
    actor_id: string;
    note: string | null;
    at: string;
  }>;
}

export interface KnowledgeInsightActionResponse {
  id: string;
  status: string;
  acknowledged_at?: string;
  resolved_at?: string;
}

export interface KnowledgeTopicRef {
  id: string;
  name: string;
}

export interface KnowledgeEvolutionStep {
  claim_id: string;
  at: string;
  statement: string;
  status: string;
  confidence: number;
  supersedes: string | null;
  replaced_by: string | null;
}

export interface KnowledgeEvolutionResponse {
  topic: KnowledgeTopicRef;
  total: number;
  steps: KnowledgeEvolutionStep[];
}

export interface KnowledgePropagationHop {
  entity_type: string;
  entity_id: string;
  title: string;
  relation: string;
  via: string;
  depth: number;
}

export interface KnowledgePropagationResponse {
  topic: KnowledgeTopicRef;
  total: number;
  depth: number;
  by_family: Record<string, number>;
  hops: KnowledgePropagationHop[];
  scope: "org" | "project";
}

export interface KnowledgeCoverageArea {
  area: string;
  coverage: number;
  total_topics: number;
  authoritative: number;
  stale: number;
  weak_reasons: string[];
}

export interface KnowledgeCoverageResponse {
  total: number;
  areas: KnowledgeCoverageArea[];
  scope: "org" | "project";
  generated_at: string;
}

export interface KnowledgeHealthBar {
  name: string;
  value: number;
  label: string;
  detail: string;
}

export interface KnowledgeDrillDown {
  contradictions: number;
  critical_gaps: number;
  unverified_claims: number;
  stale_knowledge: number;
  orphan_topics: number;
  total_topics: number;
}

export interface KnowledgeHealthCenterResponse {
  score: number;
  bars: KnowledgeHealthBar[];
  drill_down: KnowledgeDrillDown;
  why_weak: Array<{ reason: string; details: Array<Record<string, unknown>> }>;
  scope: "org" | "project";
  generated_at: string;
}

export interface KnowledgeBriefAttention {
  id: string;
  kind: string;
  title: string;
  summary: string;
  severity: string;
  priority_score: number;
}

export interface KnowledgeBriefResponse {
  since_hours: number;
  generated_at: string;
  counts: {
    significant_changes: number;
    emerging_risks: number;
    major_knowledge_gaps: number;
    decisions_potentially_affected: number;
    projects_impacted: number;
    customer_changes: number;
    strategic_signals: number;
  };
  attention: KnowledgeBriefAttention[];
  scope: "org" | "project";
}

export interface KnowledgeIntelRecommendation {
  id: string;
  kind: string;
  status: string;
  fingerprint: string;
  lifecycle: string;
  reason: string;
  confidence: number;
  risk: string;
  evidence: string[];
  entities: Array<{ type: string; id: string; name?: string }>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeRecommendationsResponse {
  total: number;
  active_kinds: string[];
  recommendations: KnowledgeIntelRecommendation[];
  scope: "org" | "project";
}

export interface KnowledgeRecommendationLifecycleResponse {
  id: string;
  kind: string;
  lifecycle: string;
  status: string;
  task_id: string | null;
  decision_id: string | null;
  audit: Array<{
    action: string;
    at: string;
    actor_id: string;
    note: string | null;
  }>;
}

export interface KnowledgeStateAtResponse {
  topic: KnowledgeTopicRef;
  as_of: string;
  state: {
    claim_id: string;
    statement: string;
    confidence: number;
    authority_level: number;
    valid_from: string;
    valid_to: string | null;
  };
  replaced_by: {
    claim_id: string;
    at: string;
    statement: string;
  } | null;
}

export interface KnowledgeGap {
  kind: string;
  topic: KnowledgeTopicRef;
  reason: string;
  confidence: number;
  severity: string;
  authority_level?: number;
  evidence: number;
  pair_ids?: string[];
}

export interface KnowledgeGapsResponse {
  total: number;
  kinds: string[];
  gaps: KnowledgeGap[];
  shortage_total: number;
  scope: "org" | "project";
}

export interface KnowledgeChangeEvent {
  kind: "new_evidence" | "understanding";
  at: string;
  family?: string;
  statement?: string;
  source_title?: string | null;
  claim_id: string;
  from?: string | null;
  to?: string;
  supersedes_claim_id?: string | null;
}

export interface KnowledgeChangesResponse {
  window_days: number;
  total: number;
  topic_changes: Array<{
    topic: KnowledgeTopicRef;
    families: string[];
    events: KnowledgeChangeEvent[];
  }>;
  scope: "org" | "project";
}

export interface KnowledgeOwnershipResponse {
  topic: KnowledgeTopicRef;
  owner: { employee_id: string | null; resolved: boolean };
  source: { type: string; id: string; title: string };
  authority: { level: number; label: string };
  last_verified_at: string | null;
  freshness_label: string;
  evidence: number;
}

export interface KnowledgeImpactResponse {
  topic: KnowledgeTopicRef & { aliases: string[] };
  evidence: {
    total: number;
    sources: Array<{
      type: string;
      id: string;
      title: string | null;
      excerpt: string;
      authority_level: number;
    }>;
  };
  affected: {
    total: number;
    by_family: Record<
      string,
      { count: number; entities: Array<{ id: string; relations: string[] }> }
    >;
  };
  dependent_knowledge: {
    total: number;
    claims: Array<Record<string, unknown>>;
  };
  scope: "org" | "project";
}

export interface KnowledgeDiscoveryAnswer {
  topic: KnowledgeTopicRef;
  score: number;
  statement: string | null;
  claim_id: string | null;
  confidence: number | null;
  authority: number;
  families: string[];
  evidence: Array<{
    claim_id: string;
    subject_type: string;
    subject_id: string;
    excerpt: string;
    source_title: string | null;
    authority_level: number;
    valid_from: string;
    matched_tokens: string[];
  }>;
}

export interface KnowledgeQueryResponse {
  question: string;
  intent: string;
  total: number;
  scope: "org" | "project";
  generated_at?: string;
  answers?: Array<KnowledgeDiscoveryAnswer | KnowledgeIntelInsight>;
  answer?: string | null;
  topic?: KnowledgeTopicRef | string;
  as_of?: string;
  state?: KnowledgeStateAtResponse["state"];
  replaced_by?: KnowledgeStateAtResponse["replaced_by"];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Slice 4E.6 — universal company actions (knowledge-to-action, governed)
// ---------------------------------------------------------------------------

export interface CompanyAction {
  id: string;
  action_type:
    "task" | "decision" | "communication" | "knowledge" | "meeting" | "project";
  title: string;
  description: string | null;
  state: string;
  risk: "low" | "medium" | "high";
  priority_score: number;
  policy: string;
  approval_required: boolean;
  approver_id: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejected_reason: string | null;
  scope_type: string;
  scope_id: string | null;
  fingerprint: string;
  target_label: string | null;
  source_problem: string | null;
  why: string | null;
  source_recommendation_id: string | null;
  source_insight_id: string | null;
  source_event_id: string | null;
  source_claim_ids: string[];
  target_type: string | null;
  target_id: string | null;
  assignee_id: string | null;
  assigned_at: string | null;
  due_at: string | null;
  overdue: boolean;
  dependencies: string[];
  escalation_level: number;
  started_at: string | null;
  blocked_at: string | null;
  blocked_reason: string | null;
  completed_at: string | null;
  verified_at: string | null;
  verification_note: string | null;
  fail_reason: string | null;
  cancel_reason: string | null;
  supersedes_id: string | null;
  superseded_by_id: string | null;
  outcome_id: string | null;
  version: number;
  attention_reasons: string[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
  deduplicated?: boolean;
}

export interface CompanyActionCenterResponse {
  total: number;
  scope: "org" | "project";
  stats: {
    by_state: Record<string, number>;
    by_action_type: Record<string, number>;
    open: number;
  };
  items: CompanyAction[];
  limit: number;
  offset: number;
}

export interface CompanyActionEvent {
  event: string;
  actor_id: string;
  note: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface CompanyActionDetailResponse extends Omit<
  CompanyAction,
  "dependencies"
> {
  events: CompanyActionEvent[];
  dependencies: Array<{
    id: string;
    title: string | null;
    state: string | null;
    complete: boolean;
  }>;
  outcome: {
    id: string;
    outcome_type: string;
    verdict: string | null;
    effectiveness: number;
    evidence: string[];
    notes: string | null;
    recorded_by: string | null;
    measured_at: string;
  } | null;
  source_recommendation?: {
    id: string;
    kind: string;
    reason: string;
    confidence: number;
    risk: string;
  } | null;
  source_insight?: {
    id: string;
    kind: string;
    title: string;
    summary: string;
  } | null;
}

export interface CompanyActionOutcomeRow {
  key: string;
  total: number;
  success: number;
  failed: number;
  avg_effectiveness: number;
}

export interface CompanyActionOutcomeIntelligence {
  total: number;
  by_outcome_type: CompanyActionOutcomeRow[];
  by_action_type: CompanyActionOutcomeRow[];
  by_risk: CompanyActionOutcomeRow[];
  success_rate: number;
  avg_effectiveness: number;
  recent: Array<{
    action_id: string;
    action_title: string | null;
    outcome_type: string;
    verdict: string | null;
    effectiveness: number;
    measured_at: string;
  }>;
}

// ---------------------------------------------------------------------------
// Gate 25 — Universal Company Workspace + Virtual Office Operating Fabric
// ---------------------------------------------------------------------------

// My Day - Employee Daily Operating Surface
export interface MyDayUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface MyDayMeeting {
  id: string;
  title: string;
  start_at: string | null;
  end_at: string | null;
  location: string | null;
  meeting_code: string;
}

export interface MyDayCommitment {
  id: string;
  title: string;
  due_at: string | null;
  state: string;
}

export interface MyDayTask {
  id: string;
  title: string;
  status: string;
  due_at: string | null;
  project_id: string | null;
}

export interface MyDayBlockedWork {
  id: string;
  title: string;
  blocked_reason: string | null;
}

export interface MyDayApproval {
  id: string;
  title: string;
  action_type: string;
}

export interface MyDayAttentionSignal {
  type: string;
  message: string;
}

export interface MyDayCapacityContext {
  utilization: number;
  allocated_hours: number;
  meeting_hours: number;
  capacity_hours: number;
}

export interface MyDayRelevantChange {
  description: string | null;
  timestamp: string | null;
}

export interface MyDay {
  date: string;
  user: MyDayUser;
  meetings: MyDayMeeting[];
  commitments: MyDayCommitment[];
  tasks: MyDayTask[];
  blocked_work: MyDayBlockedWork[];
  approvals: MyDayApproval[];
  important_communications: any[];
  attention_signals: MyDayAttentionSignal[];
  capacity_context: MyDayCapacityContext;
  relevant_changes: MyDayRelevantChange[];
}

// Company Home - Executive/Company-Wide Operating Surface
export interface CompanyHomeOrganization {
  id: string;
  name: string;
  slug: string;
}

export interface CompanyHomeStrategy {
  goals_count: number;
  objectives_count: number;
}

export interface CompanyHomeExecution {
  active_projects: number;
  active_commitments: number;
  completion_rate: number;
}

export interface CompanyHomeCustomers {
  total: number;
  at_risk: number;
  new_this_month: number;
}

export interface CompanyHomeFinancialState {
  revenue: number;
  expenses: number;
  cash_position: number;
}

export interface CompanyHomeOperations {
  processes_healthy: number;
  processes_degraded: number;
}

export interface CompanyHomePeople {
  total_employees: number;
  capacity_utilization: number;
  open_roles: number;
}

export interface CompanyHomeCapacity {
  utilization: number;
  bottlenecks: any[];
}

export interface CompanyHomeResources {
  allocated: number;
  available: number;
}

export interface CompanyHomeProcurement {
  pending_pos: number;
  vendor_risks: number;
}

export interface CompanyHomeRisk {
  id: string;
  title: string;
  severity: string;
  status: string;
}

export interface CompanyHomePrediction {
  id: string;
  title: string;
  confidence: number;
}

export interface CompanyHomeDecision {
  id: string;
  title: string;
  state: string;
}

export interface CompanyHome {
  organization: CompanyHomeOrganization;
  strategy: CompanyHomeStrategy;
  objectives: any[];
  execution: CompanyHomeExecution;
  customers: CompanyHomeCustomers;
  financial_state: CompanyHomeFinancialState;
  operations: CompanyHomeOperations;
  people: CompanyHomePeople;
  capacity: CompanyHomeCapacity;
  resources: CompanyHomeResources;
  procurement: CompanyHomeProcurement;
  risks: CompanyHomeRisk[];
  predictions: CompanyHomePrediction[];
  decisions: CompanyHomeDecision[];
  company_brain: any;
}

// Manager Workspace - Team Projection
export interface ManagerTeam {
  id: string;
  name: string;
  description: string | null;
}

export interface ManagerPerson {
  id: string;
  name: string;
  role: string;
  email: string;
}

export interface ManagerWorkspace {
  team: ManagerTeam;
  people: ManagerPerson[];
  capacity: any;
  responsibilities: any[];
  commitments: any[];
  projects: any[];
  tasks: any[];
  dependencies: any[];
  bottlenecks: any[];
  communication: any;
  risks: any[];
  performance_context: any;
}

// Universal Search
export interface UniversalSearchResult {
  id: string;
  type: string;
  title: string;
  subtitle: string | null;
  description: string | null;
  metadata: Record<string, any>;
  score: number;
  deep_link: string;
}

export interface UniversalSearchResponse {
  query: string;
  results: UniversalSearchResult[];
  total: number;
  took_ms: number;
}

// Universal Command
export interface CommandRequest {
  command: string;
  context?: Record<string, any>;
}

export interface CommandResponse {
  intent: string;
  interpretation: string;
  actions: Array<{ type: string; params: Record<string, any> }>;
  requires_authorization: boolean;
  confirmation_required: boolean;
  result?: Record<string, any>;
}

// Deep Link
export interface DeepLinkResolveRequest {
  path: string;
  params?: Record<string, any>;
}

export interface DeepLinkResolveResponse {
  target_type: string;
  target_id: string | null;
  target_url: string;
  canonical_data: Record<string, any> | null;
}

// Notifications
export interface NotificationCenterNotification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  priority: string;
  is_read: boolean;
  created_at: string | null;
  link: string | null;
}

export interface NotificationCenterResponse {
  notifications: NotificationCenterNotification[];
  unread_count: number;
  grouped: Record<string, NotificationCenterNotification[]>;
}

// Workspace Settings / Personalization
export interface WorkspaceSettingsPinnedItem {
  type: string;
  id: string;
  label: string;
}

export interface WorkspaceSettingsShortcut {
  key: string;
  label: string;
  href: string;
}

export interface WorkspaceSettingsNotificationPreferences {
  [key: string]: {
    enabled: boolean;
    channels: string[];
  };
}

export interface WorkspaceSettingsFavoriteView {
  name: string;
  href: string;
  filters: Record<string, any>;
}

export interface WorkspaceSettings {
  pinned_items: WorkspaceSettingsPinnedItem[];
  shortcuts: WorkspaceSettingsShortcut[];
  navigation_arrangement: Record<string, any>;
  dashboard_arrangement: Record<string, any>;
  notification_preferences: WorkspaceSettingsNotificationPreferences;
  favorite_views: WorkspaceSettingsFavoriteView[];
  theme: string;
  locale: string;
}

// Joy & Break Games
export interface GameSession {
  id: string;
  game_id: string;
  state: Record<string, any>;
  completed_at: string | null;
  final_score: number | null;
  started_at: string;
}

// Virtual Office
export interface WorkspaceSession {
  id: string;
  active: boolean;
  context_type: string | null;
  context_id: string | null;
  virtual_location: string | null;
  device_type: string;
  platform: string | null;
  app_version: string | null;
  last_activity_at: string;
  connected_at: string;
  disconnected_at: string | null;
}

export interface VirtualOfficeFloor {
  id: string;
  name: string;
  description: string | null;
  layout_json: Record<string, any> | null;
  background_url: string | null;
  is_default: boolean;
  capacity: number;
  access_level: string;
  allowed_departments: string[];
  allowed_teams: string[];
}

export interface VirtualOfficeRoom {
  id: string;
  floor_id: string;
  name: string;
  description: string | null;
  room_type: string;
  capacity: number;
  icon: string;
  color: string;
  requires_booking: boolean;
  auto_release_minutes: number;
  has_screen: boolean;
  has_whiteboard: boolean;
  has_video_conf: boolean;
}
