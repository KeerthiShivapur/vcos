/**
 * VCOS TypeScript API contracts — mirror of the backend OpenAPI schemas (Phase 1).
 */

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
  workspace: {
    id: string;
    daily_goal: string | null;
    onboarding_completed: boolean;
    items: { id: string; kind: string; title: string; pinned: boolean; created_at: string }[];
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
// Phase 2 — People & Organization
// ---------------------------------------------------------------------------

export interface EmployeeSummary {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string | null;
  display_name: string | null;
  full_name: string;
  email: string;
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
  recent_joins: { employee_id: string; name: string; designation: string | null; employee_number: string; joining_date: string | null }[];
  recent_transfers: { employee_id: string; title: string; description: string | null; occurred_at: string }[];
  department_distribution: { department_id: string; name: string; count: number }[];
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
// Phase 3 — Work Execution Engine
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
  ai_summary: string | null;
  dependencies: { id: string; depends_on_task_id: string; depends_on_title: string; kind: string }[] | null;
  blocking_tasks: { id: string; task_id: string; title: string; status: string }[] | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Dependency {
  id: string;
  task_id: string;
  depends_on_task_id: string;
  depends_on_title: string | null;
  kind: string;
  created_at: string | null;
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

export interface Meeting {
  id: string;
  title: string;
  description: string | null;
  meeting_type: string;
  status: string;
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
  session_id: string;
  employee_id: string;
  name: string | null;
  designation: string | null;
  avatar_url: string | null;
  role: string;
  status: string;
  device: string | null;
  mic_enabled: boolean;
  camera_enabled: boolean;
  screen_sharing: boolean;
  is_present: boolean;
  joined_at: string | null;
  left_at: string | null;
  last_active_at: string | null;
  speaking_seconds: number;
  messages_count: number;
  raised_hand: boolean;
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
  recent: { id: string; title: string; status: string; created_at: string | null }[];
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
  today_tasks: { id: string; title: string; status: string; due_date: string | null }[];
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
// Phase 4 — Knowledge Operating System
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

export interface Decision extends KnowledgeBase {
  context: string | null;
  decision_maker_id: string | null;
  decision_maker_name: string | null;
  decision_date: string | null;
  impact: string | null;
  business_impact: string | null;
  follow_up_actions: string[] | null;
  future_review_date: string | null;
  lessons_learned: string | null;
  project_id: string | null;
  project_name: string | null;
  meeting_id: string | null;
  department_id: string | null;
  decided_at: string | null;
  options: DecisionOption[];
  participants: DecisionParticipant[];
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
  top_viewed: { id: string; kind: string; title: string; url: string; views: number }[];
  top_contributors: { employee_id: string; name: string; count: number }[];
  category_coverage: Record<string, unknown>[];
  department_health: Record<string, unknown>[];
  outdated: { id: string; type: string; title: string; status: string; url: string; updated_at: string | null }[];
  review_backlog: { id: string; kind: string; title: string; url: string; status: string }[];
  quality_distribution: Record<string, number>;
  expert_distribution: Record<string, unknown>[];
  search_trends: Record<string, unknown>[];
  duplicates: { entity_type: string; entity_id: string; duplicate_of: string }[];
  coverage: { projects_with_knowledge: number };
  quality_lowest: { id: string; entity_type: string; entity_id: string; score: number; issues: string[] }[];
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
// Phase 5 — Communication & Community
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
  options: { option_id: string; text: string; vote_count: number; percentage: number }[];
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
  my_registration: { id: string; team_name: string | null; role: string; status: string } | null;
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
  top_communities: { community_id: string; name: string; type: string; member_count: number; post_count: number }[];
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
