/**
 * VCOS API client.
 *
 * Single source of truth for all backend communication:
 *  - access token held in memory
 *  - refresh token persisted (localStorage)
 *  - automatic refresh on 401 with single-flight concurrency
 *  - typed errors with the backend `detail` message
 */

import type {
  ActionItem,
  AgendaItem,
  Announcement,
  AnnouncementReceipt,
  Approval,
  ApprovalPolicy,
  Attendee,
  Availability,
  Badge,
  BrainAnswer,
  BrainAnswerRequest,
  BrainGraphTraversal,
  BrainKnowledgeSearchRequest,
  BrainKnowledgeSearchResponse,
  BrainMemory,
  BrainMemoryEvidenceResponse,
  BrainMemoryFeedResponse,
  BrainMemoryOutcomeRequest,
  BrainMemoryRelatedResponse,
  BrainMemorySearchResponse,
  BrainMemoryTimelineResponse,
  BrainPattern,
    BrainPatternEvidenceResponse,
    BrainPatternHistoryResponse,
    BrainPatternRelatedResponse,
    BrainInsight,
    BrainInsightEvidenceResponse,
    BrainInsightHistoryResponse,
    BrainInsightRelatedResponse,
    BrainInsightsListResponse,
  BrainPatternsListResponse,
  CalendarEvent,
  CalendarFeedItem,
  ChatMessage,
  Community,
  CommunityAnalytics,
  CommunityEvent,
  CommunityMember,
  Conversation,
  ConversationMember,
  Decision,
  Department,
  DepartmentStats,
  Dependency,
  Document,
  EffectivePermissions,
  Employee,
  EmployeeBadge,
  EmployeeSummary,
  Epic,
  EventRegistration,
  ExecutiveDashboard,
  Expert,
  ExpertiseScore,
  ForumReply,
  ForumThread,
  Goal,
  GovernanceAssignment,
  GovernanceDelegation,
  GovernanceScope,
  Idea,
  KeyResult,
  KnowledgeAnalytics,
  KnowledgeCategory,
  KnowledgeComment,
  KnowledgeExpert,
  KnowledgeGraph,
  KnowledgePresence,
  KnowledgeRecommendation,
  KnowledgeRecentItem,
  KnowledgeRelation,
  KnowledgeSearchResponse,
  KnowledgeTag,
  KnowledgeVersion,
  KnowledgeWatcher,
  LoginResult,
  Meeting,
  MeetingAnalyticsOverview,
  MeetingAttendanceResponse,
  MeetingCaption,
  MeetingChatMessage,
  MeetingDecision,
  MeetingNote,
  MeetingParticipant,
  MeetingRecording,
  MeetingRoom,
  MeetingSession,
  MeetingSuggestionsResponse,
  MeetingTranscript,
  MeetingWhiteboard,
  MeetingWithSession,
  Mentor,
  Message,
  Milestone,
  MyWork,
  OrgChartResponse,
  OrganizationGraph,
  OrganizationLoad,
  OrganizationStructure,
  OrgIntelligence,
  Paginated,
  Policy,
  Poll,
  PollResult,
  Post,
  PostComment,
  Presence,
  Project,
  ProjectHealth,
  ProjectMember,
  ProjectStats,
  Recognition,
  Risk,
  Roadmap,
  Role,
  SearchResponse,
  Skill,
  SkillGap,
  SOP,
  Sprint,
  Successor,
  Task,
  TaskActivityEntry,
  TaskAttachment,
  TaskComment,
  Team,
  TeamLoadSummary,
  Template,
  TimelineEntry,
  TokenPair,
  WikiPage,
  WikiTreeNode,
  Workload,
} from "@/types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8999/api/v1";

const ACCESS_KEY = "vcos.access_token";
const REFRESH_KEY = "vcos.refresh_token";
const USER_KEY = "vcos.user";
const ORG_KEY = "vcos.org";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

let accessToken: string | null = null;
let refreshPromise: Promise<TokenPair> | null = null;

// The access token lives in memory but is also hydrated from localStorage on
// every page load. Without this, a full page load starts with a null access
// token, forcing a 401 -> refresh round-trip on the very first requests; under
// React StrictMode's double-mounted effects those concurrent round-trips race
// and one of them can wipe the session (tokenStore.clear()) mid-flight.
if (typeof window !== "undefined") {
  accessToken = window.localStorage.getItem(ACCESS_KEY);
}

export const tokenStore = {
  getAccess(): string | null {
    return accessToken;
  },
  getRefresh(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  setTokens(access: string, refresh: string) {
    accessToken = access;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACCESS_KEY, access);
      window.localStorage.setItem(REFRESH_KEY, refresh);
    }
  },
  clear() {
    accessToken = null;
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(ACCESS_KEY);
      window.localStorage.removeItem(REFRESH_KEY);
      window.localStorage.removeItem(USER_KEY);
      window.localStorage.removeItem(ORG_KEY);
    }
  },
  setUser(user: unknown) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
  },
  getUser<T>(): T | null {
    if (typeof window === "undefined") return null;
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  },
  setOrg(org: unknown) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ORG_KEY, JSON.stringify(org));
    }
  },
  getOrg<T>(): T | null {
    if (typeof window === "undefined") return null;
    const raw = window.localStorage.getItem(ORG_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  },
};

// Requests normally complete in well under a second against the local backend,
// but this Windows/Chromium build occasionally drops an in-flight request at
// initiation: it never reaches the wire and the resulting fetch promise never
// settles (or rejects with TypeError). Without a cap, callers hang on disabled
// buttons and "Opening your company" forever. Each attempt is hard-capped
// (10s: a cold API worker can take several seconds on first-time requests
// like org registration; the 2.5s cap aborted those mid-flight).
// Only idempotent GETs are retried: a timed-out mutation may still be applied
// server-side, so re-sending a POST/PATCH/DELETE could duplicate state.
const ATTEMPT_TIMEOUT_MS = 10_000;
const ATTEMPT_RETRY_DELAY_MS = 400;

function isNetworkError(err: unknown): boolean {
  return (
    err instanceof TypeError ||
    (err instanceof DOMException && err.name === "AbortError")
  );
}

async function fetchWithRetry(
  url: string,
  init: RequestInit,
  allowRetry: boolean
): Promise<Response> {
  for (let attempt = 1; ; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS);
    try {
      const response = await fetch(url, { ...init, signal: controller.signal });
      clearTimeout(timer);
      return response;
    } catch (err) {
      clearTimeout(timer);
      if (!allowRetry || attempt >= 2 || !isNetworkError(err)) throw err;
      await new Promise((resolve) => setTimeout(resolve, ATTEMPT_RETRY_DELAY_MS));
    }
  }
}

async function refreshTokens(): Promise<TokenPair> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = tokenStore.getRefresh();
      if (!refresh) throw new ApiError(401, "No refresh token");
      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
        signal: AbortSignal.timeout(ATTEMPT_TIMEOUT_MS),
      });
      if (!response.ok) {
        tokenStore.clear();
        throw new ApiError(401, "Session expired");
      }
      const data = (await response.json()) as TokenPair;
      tokenStore.setTokens(data.access_token, refresh);
      return data;
    })();
  }
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export function isAuthenticated(): boolean {
  return Boolean(tokenStore.getRefresh());
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  auth?: boolean;
  retry?: boolean;
}

export async function api<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, query, auth = true, retry } = options;
  const canRefreshReissue = retry ?? true;
  const allowRetry = retry ?? method === "GET";
  const url = new URL(`${API_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const response = await fetchWithRetry(
    url.toString(),
    {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    },
    allowRetry
  );

  if (response.status === 401 && auth && canRefreshReissue) {
    try {
      const pair = await refreshTokens();
      accessToken = pair.access_token;
      return api<T>(path, { ...options, retry: false });
    } catch {
      throw new ApiError(401, "Authentication required");
    }
  }

  if (!response.ok) {
    let detail: unknown = null;
    try {
      const data = await response.json();
      detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: any) => d.msg).join("; ")
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, message, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function setSession(data: LoginResult) {
  tokenStore.setTokens(data.access_token, data.refresh_token);
  tokenStore.setUser(data.user);
  tokenStore.setOrg(data.organization);
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const data = await api<LoginResult>("/auth/login", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
  setSession(data);
  return data;
}

export async function registerOrganization(payload: {
  organization_name: string;
  organization_slug: string;
  industry?: string;
  country?: string;
  timezone?: string;
  currency?: string;
  full_name: string;
  email: string;
  username?: string;
  password: string;
}): Promise<LoginResult> {
  const data = await api<LoginResult>("/auth/register", {
    method: "POST",
    auth: false,
    body: payload,
  });
  setSession(data);
  return data;
}

export async function registerFromInvite(payload: {
  token: string;
  full_name: string;
  username?: string;
  password: string;
}): Promise<LoginResult> {
  const data = await api<LoginResult>("/auth/register/invite", {
    method: "POST",
    auth: false,
    body: payload,
  });
  setSession(data);
  return data;
}

export async function logout(allDevices = false): Promise<void> {
  try {
    await api<Message>("/auth/logout", {
      method: "POST",
      body: { refresh_token: tokenStore.getRefresh(), all_devices: allDevices },
    });
  } finally {
    tokenStore.clear();
  }
}

export async function search(query: string): Promise<SearchResponse> {
  return api<SearchResponse>("/search", { query: { q: query } });
}

// ---------------------------------------------------------------------------
// Phase 2 â€” People & Organization
// ---------------------------------------------------------------------------

export interface EmployeeListQuery {
  search?: string;
  department_id?: string;
  team_id?: string;
  location_id?: string;
  business_unit_id?: string;
  skill?: string;
  availability?: string;
  presence?: string;
  status?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export async function listEmployees(query: EmployeeListQuery = {}): Promise<EmployeeSummary[]> {
  return api<EmployeeSummary[]>("/employees", { query: query as Record<string, string | number | boolean | null | undefined> });
}

export async function getEmployee(id: string): Promise<Employee> {
  return api<Employee>(`/employees/${id}`);
}

export async function getMyEmployee(): Promise<Employee> {
  return api<Employee>("/employees/me");
}

export async function getEmployeeTimeline(id: string, limit = 50): Promise<TimelineEntry[]> {
  return api<TimelineEntry[]>(`/employees/${id}/timeline`, { query: { limit } });
}

export async function getDirectReports(id: string): Promise<EmployeeSummary[]> {
  return api<EmployeeSummary[]>(`/employees/${id}/reports`);
}

export async function getColleagues(id: string): Promise<EmployeeSummary[]> {
  return api<EmployeeSummary[]>(`/employees/${id}/colleagues`);
}

export async function getMyFavorites(): Promise<EmployeeSummary[]> {
  return api<EmployeeSummary[]>("/employees/favorites");
}

export async function addFavorite(employeeId: string): Promise<Message> {
  return api<Message>(`/employees/${employeeId}/favorite`, { method: "PUT" });
}

export async function removeFavorite(employeeId: string): Promise<Message> {
  return api<Message>(`/employees/${employeeId}/favorite`, { method: "DELETE" });
}

export async function createEmployee(payload: Record<string, unknown>): Promise<Employee> {
  return api<Employee>("/employees", { method: "POST", body: payload });
}

export async function updateEmployee(id: string, payload: Record<string, unknown>): Promise<Employee> {
  return api<Employee>(`/employees/${id}`, { method: "PATCH", body: payload });
}

export async function archiveEmployee(id: string, reason?: string): Promise<Employee> {
  return api<Employee>(`/employees/${id}/archive`, { method: "POST", body: { reason } });
}

export async function addEmployeeSkill(
  id: string,
  payload: { skill_id?: string; name?: string; level: number; years_experience?: number; verified?: boolean }
) {
  return api(`/employees/${id}/skills`, { method: "POST", body: payload });
}

export async function removeEmployeeSkill(id: string, skillId: string): Promise<Message> {
  return api<Message>(`/employees/${id}/skills/${skillId}`, { method: "DELETE" });
}

export async function addEmployeeCertification(
  id: string,
  payload: Record<string, unknown>
) {
  return api(`/employees/${id}/certifications`, { method: "POST", body: payload });
}

export async function removeEmployeeCertification(id: string, certId: string): Promise<Message> {
  return api<Message>(`/employees/${id}/certifications/${certId}`, { method: "DELETE" });
}

export async function addEmployeeAchievement(id: string, payload: Record<string, unknown>) {
  return api(`/employees/${id}/achievements`, { method: "POST", body: payload });
}

export async function removeEmployeeAchievement(id: string, achievementId: string): Promise<Message> {
  return api<Message>(`/employees/${id}/achievements/${achievementId}`, { method: "DELETE" });
}

// ------------------------------------------------------------------ departments

export async function listDepartments(): Promise<Department[]> {
  return api<Department[]>("/departments");
}

export async function getDepartment(id: string): Promise<Department> {
  return api<Department>(`/departments/${id}`);
}

export async function createDepartment(payload: Record<string, unknown>): Promise<Department> {
  return api<Department>("/departments", { method: "POST", body: payload });
}

export async function updateDepartment(id: string, payload: Record<string, unknown>): Promise<Department> {
  return api<Department>(`/departments/${id}`, { method: "PATCH", body: payload });
}

export async function getDepartmentStats(id: string): Promise<DepartmentStats> {
  return api<DepartmentStats>(`/departments/${id}/stats`);
}

export async function listLocations() {
  return api(`/departments/locations`);
}

export async function createLocation(payload: Record<string, unknown>) {
  return api(`/departments/locations`, { method: "POST", body: payload });
}

export async function listBusinessUnits() {
  return api(`/departments/business-units`);
}

export async function createBusinessUnit(payload: Record<string, unknown>) {
  return api(`/departments/business-units`, { method: "POST", body: payload });
}

// ------------------------------------------------------------------ teams

export async function listTeams(): Promise<Team[]> {
  return api<Team[]>("/teams");
}

export async function getTeam(id: string): Promise<Team> {
  return api<Team>(`/teams/${id}`);
}

export async function createTeam(payload: Record<string, unknown>): Promise<Team> {
  return api<Team>("/teams", { method: "POST", body: payload });
}

export async function updateTeam(id: string, payload: Record<string, unknown>): Promise<Team> {
  return api<Team>(`/teams/${id}`, { method: "PATCH", body: payload });
}

export async function addTeamMember(teamId: string, employeeId: string, role?: string) {
  return api(`/teams/${teamId}/members`, { method: "POST", body: { employee_id: employeeId, role } });
}

export async function removeTeamMember(teamId: string, employeeId: string): Promise<Message> {
  return api<Message>(`/teams/${teamId}/members/${employeeId}`, { method: "DELETE" });
}

export async function listTeamGoals(teamId: string) {
  return api<{ id: string; team_id: string; title: string; status: string; created_at: string }[]>(
    `/teams/${teamId}/goals`
  );
}

export async function addTeamGoal(teamId: string, title: string, status = "planned") {
  return api(`/teams/${teamId}/goals`, { method: "POST", body: { title, status } });
}

// ------------------------------------------------------------------ organization

export async function getOrganizationStructure(): Promise<OrganizationStructure> {
  return api<OrganizationStructure>("/organization/structure");
}

export async function getOrgChart(departmentId?: string, teamId?: string): Promise<OrgChartResponse> {
  return api<OrgChartResponse>("/organization/chart", { query: { department_id: departmentId, team_id: teamId } });
}

export async function getOrganizationGraph(): Promise<OrganizationGraph> {
  return api<OrganizationGraph>("/organization/graph");
}

export async function getOrgIntelligence(): Promise<OrgIntelligence> {
  return api<OrgIntelligence>("/organization/intelligence");
}

// ------------------------------------------------------------------ expertise

export async function listSkills(category?: string, search?: string): Promise<Skill[]> {
  return api<Skill[]>("/expertise/skills", { query: { category, search } });
}

export async function createSkill(payload: { name: string; category?: string; description?: string }): Promise<Skill> {
  return api<Skill>("/expertise/skills", { method: "POST", body: payload });
}

export async function listSkillCategories(): Promise<string[]> {
  return api<string[]>("/expertise/skills/categories");
}

export async function getExperts(params: {
  skill_id?: string;
  skill_name?: string;
  category?: string;
  limit?: number;
} = {}): Promise<Expert[]> {
  return api<Expert[]>("/expertise/experts", { query: params });
}

export async function getEmployeeExpertise(employeeId: string): Promise<ExpertiseScore[]> {
  return api<ExpertiseScore[]>(`/expertise/employees/${employeeId}`);
}

export async function recomputeEmployeeExpertise(employeeId: string): Promise<ExpertiseScore[]> {
  return api<ExpertiseScore[]>(`/expertise/employees/${employeeId}/recompute`, { method: "POST" });
}

export async function getSuccessors(employeeId: string, limit = 5): Promise<Successor[]> {
  return api<Successor[]>(`/expertise/successors/${employeeId}`, { query: { limit } });
}

export async function getMentors(employeeId: string, limit = 5): Promise<Mentor[]> {
  return api<Mentor[]>(`/expertise/mentors/${employeeId}`, { query: { limit } });
}

export async function getSkillGaps(): Promise<SkillGap[]> {
  return api<SkillGap[]>("/expertise/gaps");
}

// ------------------------------------------------------------------ presence

export async function getMyPresence() {
  return api<{ employee_id: string; presence: Presence | null; availability: Availability | null }>("/presence/me");
}

export async function updateMyPresence(payload: { status?: string; working_hours?: Record<string, unknown>; device?: string }) {
  return api<Presence>("/presence/me/presence", { method: "PUT", body: payload });
}

export async function updateMyAvailability(payload: { status?: string; note?: string }) {
  return api<Availability>("/presence/me/availability", { method: "PUT", body: payload });
}

export async function heartbeatPresence(status = "online"): Promise<Presence> {
  return api<Presence>("/presence/heartbeat", { method: "POST", query: { status } });
}

export async function getPresenceStats() {
  return api<{ online_now: number; on_leave: number }>("/presence/stats");
}

export function apiUrl(): string {
  return API_URL;
}

// ---------------------------------------------------------------------------
// Phase 3 â€” Work Execution Engine
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------- projects

export async function listProjects(query: {
  status?: string;
  search?: string;
  sort?: string;
} = {}): Promise<Project[]> {
  return api<Project[]>("/projects", { query });
}

export async function getProject(id: string): Promise<Project> {
  return api<Project>(`/projects/${id}`);
}

export async function createProject(payload: Record<string, unknown>): Promise<Project> {
  return api<Project>("/projects", { method: "POST", body: payload });
}

export async function updateProject(id: string, payload: Record<string, unknown>): Promise<Project> {
  return api<Project>(`/projects/${id}`, { method: "PATCH", body: payload });
}

export async function deleteProject(id: string): Promise<Message> {
  return api<Message>(`/projects/${id}`, { method: "DELETE" });
}

export async function projectLifecycle(id: string, action: string): Promise<Project> {
  return api<Project>(`/projects/${id}/lifecycle`, { method: "POST", body: { action } });
}

export async function listProjectMembers(id: string): Promise<ProjectMember[]> {
  return api<ProjectMember[]>(`/projects/${id}/members`);
}

export async function addProjectMember(id: string, employeeId: string, role?: string): Promise<ProjectMember> {
  return api<ProjectMember>(`/projects/${id}/members`, { method: "POST", body: { employee_id: employeeId, role } });
}

export async function removeProjectMember(id: string, employeeId: string): Promise<Message> {
  return api<Message>(`/projects/${id}/members/${employeeId}`, { method: "DELETE" });
}

export async function getProjectStats(id: string): Promise<ProjectStats> {
  return api<ProjectStats>(`/projects/${id}/stats`);
}

export async function getProjectTimeline(id: string): Promise<TimelineEntry[]> {
  return api<TimelineEntry[]>(`/projects/${id}/timeline`);
}

export async function getProjectHealth(id: string): Promise<ProjectHealth> {
  return api<ProjectHealth>(`/projects/${id}/health`);
}

// ---------------------------------------------------------------- roadmaps

export async function listRoadmaps(): Promise<Roadmap[]> {
  return api<Roadmap[]>("/roadmaps");
}

export async function createRoadmap(payload: Record<string, unknown>): Promise<Roadmap> {
  return api<Roadmap>("/roadmaps", { method: "POST", body: payload });
}

export async function updateRoadmap(id: string, payload: Record<string, unknown>): Promise<Roadmap> {
  return api<Roadmap>(`/roadmaps/${id}`, { method: "PATCH", body: payload });
}

export async function deleteRoadmap(id: string): Promise<Message> {
  return api<Message>(`/roadmaps/${id}`, { method: "DELETE" });
}

export async function roadmapLifecycle(id: string, action: string): Promise<Roadmap> {
  return api<Roadmap>(`/roadmaps/${id}/lifecycle`, { method: "POST", body: { action } });
}

// ---------------------------------------------------------------- epics

export async function listEpics(projectId?: string): Promise<Epic[]> {
  return api<Epic[]>("/epics", { query: { project_id: projectId } });
}

export async function createEpic(payload: Record<string, unknown>): Promise<Epic> {
  return api<Epic>("/epics", { method: "POST", body: payload });
}

export async function updateEpic(id: string, payload: Record<string, unknown>): Promise<Epic> {
  return api<Epic>(`/epics/${id}`, { method: "PATCH", body: payload });
}

export async function deleteEpic(id: string): Promise<Message> {
  return api<Message>(`/epics/${id}`, { method: "DELETE" });
}

export async function startEpic(id: string): Promise<Epic> {
  return api<Epic>(`/epics/${id}/start`, { method: "POST" });
}

export async function completeEpic(id: string): Promise<Epic> {
  return api<Epic>(`/epics/${id}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- milestones

export async function listMilestones(projectId?: string): Promise<Milestone[]> {
  return api<Milestone[]>("/milestones", { query: { project_id: projectId } });
}

export async function createMilestone(payload: Record<string, unknown>): Promise<Milestone> {
  return api<Milestone>("/milestones", { method: "POST", body: payload });
}

export async function updateMilestone(id: string, payload: Record<string, unknown>): Promise<Milestone> {
  return api<Milestone>(`/milestones/${id}`, { method: "PATCH", body: payload });
}

export async function deleteMilestone(id: string): Promise<Message> {
  return api<Message>(`/milestones/${id}`, { method: "DELETE" });
}

export async function completeMilestone(id: string): Promise<Milestone> {
  return api<Milestone>(`/milestones/${id}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- sprints

export async function listSprints(projectId?: string): Promise<Sprint[]> {
  return api<Sprint[]>("/sprints", { query: { project_id: projectId } });
}

export async function createSprint(payload: Record<string, unknown>): Promise<Sprint> {
  return api<Sprint>("/sprints", { method: "POST", body: payload });
}

export async function updateSprint(id: string, payload: Record<string, unknown>): Promise<Sprint> {
  return api<Sprint>(`/sprints/${id}`, { method: "PATCH", body: payload });
}

export async function deleteSprint(id: string): Promise<Message> {
  return api<Message>(`/sprints/${id}`, { method: "DELETE" });
}

export async function startSprint(id: string): Promise<Sprint> {
  return api<Sprint>(`/sprints/${id}/start`, { method: "POST" });
}

export async function completeSprint(id: string): Promise<Sprint> {
  return api<Sprint>(`/sprints/${id}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- tasks

export async function listTasks(query: {
  project_id?: string;
  assignee_id?: string;
  parent_task_id?: string;
  sprint_id?: string;
  status?: string;
  priority?: string;
  tag?: string;
  search?: string;
  sort?: string;
} = {}): Promise<Task[]> {
  return api<Task[]>("/tasks", { query });
}

export async function getTask(id: string): Promise<Task> {
  return api<Task>(`/tasks/${id}`);
}

export async function createTask(payload: Record<string, unknown>): Promise<Task> {
  return api<Task>("/tasks", { method: "POST", body: payload });
}

export async function updateTask(id: string, payload: Record<string, unknown>): Promise<Task> {
  return api<Task>(`/tasks/${id}`, { method: "PATCH", body: payload });
}

export async function transitionTask(id: string, status: string): Promise<Task> {
  return api<Task>(`/tasks/${id}/transition`, { method: "POST", body: { status } });
}

export async function deleteTask(id: string): Promise<Message> {
  return api<Message>(`/tasks/${id}`, { method: "DELETE" });
}

export async function listTaskDependencies(taskId: string): Promise<Dependency[]> {
  return api<Dependency[]>(`/tasks/${taskId}/dependencies`);
}

export async function addTaskDependency(taskId: string, dependsOnTaskId: string, kind = "finish_to_start"): Promise<Dependency> {
  return api<Dependency>(`/tasks/${taskId}/dependencies`, {
    method: "POST",
    body: { depends_on_task_id: dependsOnTaskId, kind },
  });
}

export async function removeTaskDependency(taskId: string, dependencyId: string): Promise<Message> {
  return api<Message>(`/tasks/${taskId}/dependencies/${dependencyId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------- task collaboration

export type { TaskComment, TaskAttachment, TaskActivityEntry } from "@/types";

export async function addTaskComment(taskId: string, body: string): Promise<TaskComment> {
  return api<TaskComment>(`/tasks/${taskId}/comments`, { method: "POST", body: { body } });
}

export async function listTaskComments(taskId: string): Promise<TaskComment[]> {
  return api<TaskComment[]>(`/tasks/${taskId}/comments`);
}

export async function deleteTaskComment(taskId: string, commentId: string): Promise<Message> {
  return api<Message>(`/tasks/${taskId}/comments/${commentId}`, { method: "DELETE" });
}

export async function addTaskAttachment(
  taskId: string,
  payload: { filename: string; url: string; size_bytes?: number; kind?: string }
): Promise<TaskAttachment> {
  return api<TaskAttachment>(`/tasks/${taskId}/attachments`, { method: "POST", body: payload });
}

export async function listTaskAttachments(taskId: string): Promise<TaskAttachment[]> {
  return api<TaskAttachment[]>(`/tasks/${taskId}/attachments`);
}

export async function deleteTaskAttachment(taskId: string, attachmentId: string): Promise<Message> {
  return api<Message>(`/tasks/${taskId}/attachments/${attachmentId}`, { method: "DELETE" });
}

export async function getTaskActivity(taskId: string): Promise<TaskActivityEntry[]> {
  return api<TaskActivityEntry[]>(`/tasks/${taskId}/activity`);
}

// ---------------------------------------------------------------- goals

export async function listGoals(query: {
  scope?: string;
  status?: string;
  owner_id?: string;
  team_id?: string;
  search?: string;
} = {}): Promise<Goal[]> {
  return api<Goal[]>("/goals", { query });
}

export async function getGoal(id: string): Promise<Goal> {
  return api<Goal>(`/goals/${id}`);
}

export async function createGoal(payload: Record<string, unknown>): Promise<Goal> {
  return api<Goal>("/goals", { method: "POST", body: payload });
}

export async function updateGoal(id: string, payload: Record<string, unknown>): Promise<Goal> {
  return api<Goal>(`/goals/${id}`, { method: "PATCH", body: payload });
}

export async function deleteGoal(id: string): Promise<Message> {
  return api<Message>(`/goals/${id}`, { method: "DELETE" });
}

export async function listKeyResults(goalId: string): Promise<KeyResult[]> {
  return api<KeyResult[]>(`/goals/${goalId}/key-results`);
}

export async function addKeyResult(goalId: string, payload: Record<string, unknown>): Promise<KeyResult> {
  return api<KeyResult>(`/goals/${goalId}/key-results`, { method: "POST", body: payload });
}

export async function updateKeyResult(goalId: string, krId: string, payload: Record<string, unknown>): Promise<KeyResult> {
  return api<KeyResult>(`/goals/${goalId}/key-results/${krId}`, { method: "PATCH", body: payload });
}

export async function deleteKeyResult(goalId: string, krId: string): Promise<Message> {
  return api<Message>(`/goals/${goalId}/key-results/${krId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------- meetings

export async function listMeetings(query: {
  project_id?: string;
  status?: string;
  employee_id?: string;
} = {}): Promise<Meeting[]> {
  return api<Meeting[]>("/meetings", { query });
}

export async function getMeeting(id: string): Promise<Meeting> {
  return api<Meeting>(`/meetings/${id}`);
}

export async function createMeeting(payload: Record<string, unknown>): Promise<Meeting> {
  return api<Meeting>("/meetings", { method: "POST", body: payload });
}

export async function updateMeeting(id: string, payload: Record<string, unknown>): Promise<Meeting> {
  return api<Meeting>(`/meetings/${id}`, { method: "PATCH", body: payload });
}

export async function completeMeeting(id: string): Promise<Meeting> {
  return api<Meeting>(`/meetings/${id}/complete`, { method: "POST" });
}

export async function deleteMeeting(id: string): Promise<Message> {
  return api<Message>(`/meetings/${id}`, { method: "DELETE" });
}

// ------------------------------------------------- Phase 6: collaboration

export async function listUpcomingMeetings(query: {
  scope?: string;
  from_date?: string;
  to_date?: string;
} = {}): Promise<MeetingWithSession[]> {
  return api<MeetingWithSession[]>("/meetings/upcoming", { query });
}

export async function meetingByCode(code: string): Promise<MeetingWithSession> {
  return api<MeetingWithSession>(`/meetings/code/${code}`);
}

export async function getMeetingSession(meetingId: string): Promise<MeetingSession> {
  return api<MeetingSession>(`/meetings/${meetingId}/session`);
}

export async function createMeetingSession(meetingId: string, payload: Record<string, unknown>): Promise<MeetingSession> {
  return api<MeetingSession>(`/meetings/${meetingId}/session`, { method: "POST", body: payload });
}

export async function joinMeeting(meetingId: string, device = "desktop"): Promise<{
  meeting: Meeting;
  session: MeetingSession;
  participant: MeetingParticipant;
}> {
  return api(`/meetings/${meetingId}/join`, { method: "POST", body: { device } });
}

export async function leaveMeeting(meetingId: string): Promise<{ left: boolean; participant_id?: string }> {
  return api(`/meetings/${meetingId}/leave`, { method: "POST" });
}

export async function inviteToMeeting(meetingId: string, employeeIds: string[], message?: string): Promise<{ invited: string[]; count: number }> {
  return api(`/meetings/${meetingId}/invite`, { method: "POST", body: { employee_ids: employeeIds, message } });
}

export async function startMeetingSession(meetingId: string): Promise<MeetingSession> {
  return api<MeetingSession>(`/meetings/${meetingId}/start`, { method: "POST" });
}

export async function endMeetingSession(meetingId: string): Promise<MeetingSession> {
  return api<MeetingSession>(`/meetings/${meetingId}/end`, { method: "POST" });
}

export async function sendMeetingPresence(meetingId: string, payload: Record<string, unknown>): Promise<MeetingParticipant> {
  return api<MeetingParticipant>(`/meetings/${meetingId}/presence`, { method: "POST", body: payload });
}

export async function listMeetingParticipants(meetingId: string): Promise<MeetingParticipant[]> {
  return api<MeetingParticipant[]>(`/meetings/${meetingId}/participants`);
}

export async function listMeetingNotes(meetingId: string): Promise<MeetingNote[]> {
  return api<MeetingNote[]>(`/meetings/${meetingId}/notes`);
}

export async function createMeetingNote(meetingId: string, content: string, sessionId?: string): Promise<MeetingNote> {
  return api<MeetingNote>(`/meetings/${meetingId}/notes`, { method: "POST", body: { content, session_id: sessionId } });
}

export async function updateMeetingNote(meetingId: string, noteId: string, content: string): Promise<MeetingNote> {
  return api<MeetingNote>(`/meetings/${meetingId}/notes/${noteId}`, { method: "PATCH", body: { content } });
}

export async function deleteMeetingNote(meetingId: string, noteId: string): Promise<Message> {
  return api<Message>(`/meetings/${meetingId}/notes/${noteId}`, { method: "DELETE" });
}

export async function listMeetingRooms(query: {
  room_type?: string;
  status?: string;
  department_id?: string;
  team_id?: string;
} = {}): Promise<MeetingRoom[]> {
  return api<MeetingRoom[]>("/meeting-rooms", { query });
}

export async function getMeetingRoom(id: string): Promise<MeetingRoom> {
  return api<MeetingRoom>(`/meeting-rooms/${id}`);
}

export async function createMeetingRoom(payload: Record<string, unknown>): Promise<MeetingRoom> {
  return api<MeetingRoom>("/meeting-rooms", { method: "POST", body: payload });
}

export async function updateMeetingRoom(id: string, payload: Record<string, unknown>): Promise<MeetingRoom> {
  return api<MeetingRoom>(`/meeting-rooms/${id}`, { method: "PATCH", body: payload });
}

export async function deleteMeetingRoom(id: string): Promise<Message> {
  return api<Message>(`/meeting-rooms/${id}`, { method: "DELETE" });
}

export async function roomAvailability(id: string, start?: string, end?: string): Promise<
  { kind: string; id: string; title: string; start_at: string | null; end_at: string | null; status: string }[]
> {
  return api(`/meeting-rooms/${id}/availability`, { query: { start, end } });
}

export async function listMeetingAttendees(meetingId: string): Promise<Attendee[]> {
  return api<Attendee[]>(`/meetings/${meetingId}/attendees`);
}

export async function addMeetingAttendee(meetingId: string, employeeId: string, role = "participant"): Promise<Attendee> {
  return api<Attendee>(`/meetings/${meetingId}/attendees`, { method: "POST", body: { employee_id: employeeId, role } });
}

export async function removeMeetingAttendee(meetingId: string, employeeId: string): Promise<Message> {
  return api<Message>(`/meetings/${meetingId}/attendees/${employeeId}`, { method: "DELETE" });
}

export async function rsvpMeeting(meetingId: string, status: "accepted" | "declined" | "tentative"): Promise<Attendee> {
  return api<Attendee>(`/meetings/${meetingId}/rsvp`, { method: "POST", body: { status } });
}

export async function listAgendaItems(meetingId: string): Promise<AgendaItem[]> {
  return api<AgendaItem[]>(`/meetings/${meetingId}/agenda`);
}

export async function addAgendaItem(meetingId: string, payload: Record<string, unknown>): Promise<AgendaItem> {
  return api<AgendaItem>(`/meetings/${meetingId}/agenda`, { method: "POST", body: payload });
}

export async function listActionItems(meetingId: string): Promise<ActionItem[]> {
  return api<ActionItem[]>(`/meetings/${meetingId}/action-items`);
}

export async function addActionItem(meetingId: string, payload: Record<string, unknown>): Promise<ActionItem> {
  return api<ActionItem>(`/meetings/${meetingId}/action-items`, { method: "POST", body: payload });
}

export async function completeActionItem(meetingId: string, itemId: string): Promise<ActionItem> {
  return api<ActionItem>(`/meetings/${meetingId}/action-items/${itemId}/complete`, { method: "POST" });
}

// ------------------------------------------- Phase 6: live collaboration (chat/whiteboard/captions)

export async function listMeetingChat(meetingId: string, limit = 50): Promise<MeetingChatMessage[]> {
  return api<MeetingChatMessage[]>(`/meetings/${meetingId}/chat`, { query: { limit } });
}

export async function sendMeetingChat(meetingId: string, content: string): Promise<MeetingChatMessage> {
  return api<MeetingChatMessage>(`/meetings/${meetingId}/chat`, { method: "POST", body: { content } });
}

export async function deleteMeetingChat(meetingId: string, messageId: string): Promise<Message> {
  return api<Message>(`/meetings/${meetingId}/chat/${messageId}`, { method: "DELETE" });
}

export async function getMeetingWhiteboard(meetingId: string): Promise<MeetingWhiteboard> {
  return api<MeetingWhiteboard>(`/meetings/${meetingId}/whiteboard`);
}

export async function updateMeetingWhiteboard(
  meetingId: string,
  content: Record<string, unknown>,
  version: number
): Promise<MeetingWhiteboard> {
  return api<MeetingWhiteboard>(`/meetings/${meetingId}/whiteboard`, {
    method: "PUT",
    body: { content, version },
  });
}

export async function listMeetingCaptions(
  meetingId: string,
  afterMs?: number,
  language?: string
): Promise<MeetingCaption[]> {
  return api<MeetingCaption[]>(`/meetings/${meetingId}/captions`, {
    query: { after_ms: afterMs, language },
  });
}

export async function addMeetingCaption(
  meetingId: string,
  payload: {
    text: string;
    employee_id?: string;
    language?: string;
    start_ms?: number;
    end_ms?: number;
  }
): Promise<MeetingCaption> {
  return api<MeetingCaption>(`/meetings/${meetingId}/captions`, { method: "POST", body: payload });
}

export async function getMeetingTranscript(meetingId: string): Promise<MeetingTranscript | { meeting_id: string; status: string }> {
  return api<MeetingTranscript | { meeting_id: string; status: string }>(`/meetings/${meetingId}/transcript`);
}

// ------------------------------------------- Phase 6: recordings

export async function listMeetingRecordings(meetingId: string): Promise<MeetingRecording[]> {
  return api<MeetingRecording[]>(`/meetings/${meetingId}/recordings`);
}

export async function startMeetingRecording(
  meetingId: string,
  payload: { kind?: string; title?: string; captions_enabled?: boolean; language?: string } = {}
): Promise<MeetingRecording> {
  return api<MeetingRecording>(`/meetings/${meetingId}/recordings/start`, { method: "POST", body: payload });
}

export async function stopMeetingRecording(meetingId: string, recordingId: string): Promise<MeetingRecording> {
  return api<MeetingRecording>(`/meetings/${meetingId}/recordings/${recordingId}/stop`, { method: "POST" });
}

export async function deleteMeetingRecording(meetingId: string, recordingId: string): Promise<Message> {
  return api<Message>(`/meetings/${meetingId}/recordings/${recordingId}`, { method: "DELETE" });
}

export async function listRecordingLibrary(status?: string, limit = 100): Promise<MeetingRecording[]> {
  return api<MeetingRecording[]>("/recordings", { query: { status, limit } });
}

// ------------------------------------------- Phase 6: meeting intelligence

export async function finalizeMeetingIntelligence(meetingId: string): Promise<Record<string, unknown>> {
  return api<Record<string, unknown>>(`/meetings/${meetingId}/ai/finalize`, { method: "POST" });
}

export async function getMeetingAttendance(meetingId: string): Promise<MeetingAttendanceResponse> {
  return api<MeetingAttendanceResponse>(`/meetings/${meetingId}/attendance`);
}

export async function listMeetingDecisions(meetingId: string): Promise<MeetingDecision[]> {
  return api<MeetingDecision[]>(`/meetings/${meetingId}/decisions`);
}

export async function createMeetingDecision(meetingId: string, content: string): Promise<MeetingDecision> {
  return api<MeetingDecision>(`/meetings/${meetingId}/decisions`, { method: "POST", body: { content } });
}

export async function updateMeetingDecision(
  meetingId: string,
  decisionId: string,
  content: string
): Promise<MeetingDecision> {
  return api<MeetingDecision>(`/meetings/${meetingId}/decisions/${decisionId}`, {
    method: "PATCH",
    body: { content },
  });
}

export async function deleteMeetingDecision(meetingId: string, decisionId: string): Promise<Message> {
  return api<Message>(`/meetings/${meetingId}/decisions/${decisionId}`, { method: "DELETE" });
}

export async function getMeetingSuggestions(query: {
  employee_ids?: string;
  duration_minutes?: number;
  days?: number;
  start_at?: string;
  end_at?: string;
  capacity?: number;
} = {}): Promise<MeetingSuggestionsResponse> {
  return api<MeetingSuggestionsResponse>("/meetings/suggest", { query });
}

export async function getMeetingAnalyticsOverview(days = 30): Promise<MeetingAnalyticsOverview> {
  return api<MeetingAnalyticsOverview>("/meeting-analytics", { query: { days } });
}

// ---------------------------------------------------------------- calendar

export async function listCalendarEvents(query: {
  employee_id?: string;
  start?: string;
  end?: string;
  scope?: string;
  project_id?: string;
  team_id?: string;
} = {}): Promise<CalendarEvent[]> {
  return api<CalendarEvent[]>("/calendar/events", { query });
}

export async function getCalendarFeed(query: {
  start?: string;
  end?: string;
  employee_id?: string;
} = {}): Promise<CalendarFeedItem[]> {
  return api<CalendarFeedItem[]>("/calendar/feed", { query });
}

export async function createCalendarEvent(payload: Record<string, unknown>): Promise<CalendarEvent> {
  return api<CalendarEvent>("/calendar/events", { method: "POST", body: payload });
}

export async function updateCalendarEvent(id: string, payload: Record<string, unknown>): Promise<CalendarEvent> {
  return api<CalendarEvent>(`/calendar/events/${id}`, { method: "PATCH", body: payload });
}

export async function deleteCalendarEvent(id: string): Promise<Message> {
  return api<Message>(`/calendar/events/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------- approvals

export async function listApprovals(query: {
  status?: string;
  approval_type?: string;
  employee_id?: string;
} = {}): Promise<Approval[]> {
  return api<Approval[]>("/approvals", { query });
}

export async function createApproval(payload: Record<string, unknown>): Promise<Approval> {
  return api<Approval>("/approvals", { method: "POST", body: payload });
}

export async function decideApproval(id: string, decision: "approved" | "rejected", note?: string): Promise<Approval> {
  return api<Approval>(`/approvals/${id}/decide`, { method: "POST", body: { decision, note } });
}

export async function cancelApproval(id: string): Promise<Approval> {
  return api<Approval>(`/approvals/${id}/cancel`, { method: "POST" });
}

export async function getApprovalStats() {
  return api<Record<string, unknown>>("/approvals/stats");
}

// ---------------------------------------------------------------- risks

export async function listRisks(query: {
  project_id?: string;
  status?: string;
  severity?: string;
} = {}): Promise<Risk[]> {
  return api<Risk[]>("/risks", { query });
}

export async function createRisk(payload: Record<string, unknown>): Promise<Risk> {
  return api<Risk>("/risks", { method: "POST", body: payload });
}

export async function updateRisk(id: string, payload: Record<string, unknown>): Promise<Risk> {
  return api<Risk>(`/risks/${id}`, { method: "PATCH", body: payload });
}

export async function closeRisk(id: string): Promise<Risk> {
  return api<Risk>(`/risks/${id}/close`, { method: "POST" });
}

export async function deleteRisk(id: string): Promise<Message> {
  return api<Message>(`/risks/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------- governance

export async function listGovernanceScopes(): Promise<GovernanceScope[]> {
  return api<GovernanceScope[]>("/governance/scopes");
}

export async function listRoles(): Promise<Role[]> {
  return api<Role[]>("/roles");
}

export async function createGovernanceScope(payload: Record<string, unknown>): Promise<GovernanceScope> {
  return api<GovernanceScope>("/governance/scopes", { method: "POST", body: payload });
}

export async function updateGovernanceScope(id: string, payload: Record<string, unknown>): Promise<GovernanceScope> {
  return api<GovernanceScope>(`/governance/scopes/${id}`, { method: "PATCH", body: payload });
}

export async function deleteGovernanceScope(id: string): Promise<Message> {
  return api<Message>(`/governance/scopes/${id}`, { method: "DELETE" });
}

export async function listGovernanceAssignments(query: {
  user_id?: string;
  scope_id?: string;
  role_id?: string;
} = {}): Promise<GovernanceAssignment[]> {
  return api<GovernanceAssignment[]>("/governance/assignments", { query });
}

export async function createGovernanceAssignment(payload: Record<string, unknown>): Promise<GovernanceAssignment> {
  return api<GovernanceAssignment>("/governance/assignments", { method: "POST", body: payload });
}

export async function removeGovernanceAssignment(id: string): Promise<Message> {
  return api<Message>(`/governance/assignments/${id}`, { method: "DELETE" });
}

export async function listGovernanceDelegations(query: {
  granted_to?: string;
  granted_by?: string;
  status?: string;
} = {}): Promise<GovernanceDelegation[]> {
  return api<GovernanceDelegation[]>("/governance/delegations", { query });
}

export async function createGovernanceDelegation(payload: Record<string, unknown>): Promise<GovernanceDelegation> {
  return api<GovernanceDelegation>("/governance/delegations", { method: "POST", body: payload });
}

export async function revokeGovernanceDelegation(id: string): Promise<GovernanceDelegation> {
  return api<GovernanceDelegation>(`/governance/delegations/${id}/revoke`, { method: "POST" });
}

export async function getEffectivePermissions(userId: string, scopeId?: string): Promise<EffectivePermissions> {
  return api<EffectivePermissions>("/governance/effective-permissions", {
    query: { user_id: userId, scope_id: scopeId },
  });
}

export async function listApprovalPolicies(): Promise<ApprovalPolicy[]> {
  return api<ApprovalPolicy[]>("/governance/policies");
}

export async function createApprovalPolicy(payload: Record<string, unknown>): Promise<ApprovalPolicy> {
  return api<ApprovalPolicy>("/governance/policies", { method: "POST", body: payload });
}

export async function updateApprovalPolicy(id: string, payload: Record<string, unknown>): Promise<ApprovalPolicy> {
  return api<ApprovalPolicy>(`/governance/policies/${id}`, { method: "PATCH", body: payload });
}

// ---------------------------------------------------------------- workload & analytics

export async function getMyWorkload(): Promise<Workload> {
  return api<Workload>("/workload/me");
}

export async function getEmployeeWorkload(employeeId: string): Promise<Workload> {
  return api<Workload>(`/workload/employees/${employeeId}`);
}

export async function snapshotWorkload(): Promise<{ snapshots_created: number }> {
  return api<{ snapshots_created: number }>("/workload/snapshot", { method: "POST" });
}

export async function getOrganizationLoad(): Promise<OrganizationLoad> {
  return api<OrganizationLoad>("/workload/organization");
}

export async function getTeamLoad(): Promise<TeamLoadSummary[]> {
  return api<TeamLoadSummary[]>("/workload/teams");
}

export async function getMyWork(): Promise<MyWork> {
  return api<MyWork>("/my-work");
}

export async function getExecutiveDashboard(): Promise<ExecutiveDashboard> {
  return api<ExecutiveDashboard>("/analytics/executive");
}

// ---------------------------------------------------------------- executive intelligence (Phase 8)

export interface ExecutiveHealth {
  organization_id: string;
  score: number;
  status: "excellent" | "good" | "watch" | "at_risk";
  breakdown: Record<string, number>;
  counts: Record<string, number>;
  computed_at: string;
}

export interface DepartmentHealth {
  department_id: string;
  name: string;
  health: number;
  status: string;
  head_count: number;
  projects: number;
  open_tasks: number;
  overdue_tasks: number;
  completion_rate: number;
  velocity_per_employee: number;
  meetings: number;
  goals: number;
  goals_progress: number;
}

export interface StrategicRisk {
  id: string;
  kind: string;
  title: string;
  description: string;
  probability: number;
  impact: number;
  score: number;
  level: "critical" | "high" | "medium" | "low";
  subject_type?: string;
  subject_id?: string;
  subject_name?: string;
  affected_teams: string[];
  recommended_actions: string[];
  evidence: Record<string, unknown>;
  status: "open" | "accepted" | "mitigated";
  created_at?: string;
}

export interface ExecutiveRecommendation {
  id: string;
  kind: string;
  title: string;
  rationale: string;
  evidence: Record<string, unknown>;
  expected_outcome: string;
  confidence: number;
  impact: string;
  status: "active" | "accepted" | "dismissed";
  created_at?: string;
}

export interface ExecutivePrediction {
  id: string;
  subject_type: string;
  subject_id?: string;
  metric: string;
  score: number;
  level: "high" | "medium" | "low";
  rationale: string;
  factors: Record<string, unknown>;
  created_at?: string;
}

export interface SimulationResult {
  id?: string;
  scenario: string;
  title: string;
  params: Record<string, unknown>;
  assumptions: string[];
  baseline: Record<string, unknown>;
  results: Record<string, unknown>;
  risks: string[];
  opportunities: string[];
  simulated_at?: string;
}

export interface ExecutiveReport {
  id: string;
  report_type: string;
  title: string;
  content: string;
  generated_by?: string;
  created_at?: string;
}

export interface DigitalTwin {
  entity_counts: Record<string, number>;
  twin: {
    organization_id: string;
    captured_at: string;
    people: Record<string, unknown>;
    work: Record<string, unknown>;
    collaboration: Record<string, unknown>;
    knowledge: Record<string, unknown>;
    learning: Record<string, unknown>;
    innovation: Record<string, unknown>;
    strategy: Record<string, unknown>;
    risks: unknown[];
    graph: { nodes: number; project_memberships: number };
  };
}

export interface ExecutiveTimelineEntry {
  source: string;
  kind: string;
  title: string;
  occurred_at?: string;
  payload: Record<string, unknown>;
}

export interface MemoryMatch {
  source: "event" | "decision" | "audit" | "memory";
  id: string;
  name: string;
  occurred_at?: string;
  payload?: Record<string, unknown>;
  content?: string;
  kind?: string;
  actor?: string;
  details?: Record<string, unknown>;
}

export interface TrendSeries {
  metric: string;
  period: string;
  points: { period: string; value: number }[];
  first: number;
  last: number;
  change_percent: number;
  direction: "growing" | "declining" | "stable";
}

export interface ExecutiveMetric {
  id: string;
  metric: string;
  value: number;
  unit: string;
  period: string;
  period_start: string;
}

export interface StrategicGoal {
  id: string;
  name: string;
  description?: string;
  timeframe: string;
  status: string;
  progress: number;
  priority: string;
  focus: string;
  owner_id?: string;
  created_at?: string;
}

export interface StrategyPlan {
  horizon: string;
  company_health: number;
  status: string;
  priorities: string[];
  focus_areas: string[];
  initiatives: { title: string; why: string; evidence: Record<string, unknown> }[];
  predictions: { metric: string; level: string; rationale: string }[];
  generated_at: string;
}

export interface StrategyAnswer {
  answer: string;
  question: string;
  kind: string;
  source: string;
  evidence: Record<string, unknown>;
}

export interface ExecutiveIntelligenceDashboard {
  organization: { id: string; name: string };
  generated_at: string;
  health: ExecutiveHealth;
  summary: string;
  attention: {
    critical_risks: number;
    active_recommendations: number;
    overdue_tasks: number;
    overloaded_employees: number;
    knowledge_total: number;
  };
  departments_health: DepartmentHealth[];
  projects_health: { project_id: string; name: string; health: number; progress: number; status: string }[];
  risks: StrategicRisk[];
  recommendations: ExecutiveRecommendation[];
  digital_twin: Record<string, number>;
  executive_calendar: { id: string; title: string; start_at?: string; meeting_type: string; status: string }[];
  recent_decisions: { id: string; title: string; status: string; created_at?: string }[];
  recent_activity: ExecutiveTimelineEntry[];
  strategy: Record<string, unknown>;
}

export async function getExecutiveIntelligence(refresh = false): Promise<ExecutiveIntelligenceDashboard> {
  return api<ExecutiveIntelligenceDashboard>("/executive/dashboard", { query: { refresh } });
}

export async function getCompanyHealth(): Promise<ExecutiveHealth> {
  return api<ExecutiveHealth>("/executive/health");
}

export async function getDepartmentsHealth(): Promise<{ total: number; departments: DepartmentHealth[] }> {
  return api<{ total: number; departments: DepartmentHealth[] }>("/executive/health/departments");
}

export async function getDepartmentHealth(departmentId: string): Promise<DepartmentHealth> {
  return api<DepartmentHealth>(`/executive/health/departments/${departmentId}`);
}

export async function listStrategicRisks(query: {
  refresh?: boolean;
  status?: string;
  level?: string;
  limit?: number;
} = {}): Promise<{ total: number; risks: StrategicRisk[] }> {
  return api<{ total: number; risks: StrategicRisk[] }>("/executive/risks", { query });
}

export async function updateStrategicRiskStatus(
  riskId: string,
  status: "open" | "accepted" | "mitigated"
): Promise<StrategicRisk> {
  return api<StrategicRisk>(`/executive/risks/${riskId}/status`, { method: "PATCH", body: { status } });
}

export async function listExecutiveRecommendations(query: {
  refresh?: boolean;
  status?: string;
  limit?: number;
} = {}): Promise<{ total: number; recommendations: ExecutiveRecommendation[] }> {
  return api<{ total: number; recommendations: ExecutiveRecommendation[] }>("/executive/recommendations", { query });
}

export async function updateRecommendationStatus(
  recommendationId: string,
  status: "active" | "accepted" | "dismissed"
): Promise<ExecutiveRecommendation> {
  return api<ExecutiveRecommendation>(`/executive/recommendations/${recommendationId}/status`, {
    method: "PATCH",
    body: { status },
  });
}

export async function listExecutivePredictions(query: {
  refresh?: boolean;
  metric?: string;
  level?: string;
} = {}): Promise<{ total: number; predictions: ExecutivePrediction[] }> {
  return api<{ total: number; predictions: ExecutivePrediction[] }>("/executive/predictions", { query });
}

export async function runSimulation(
  scenario: string,
  params: Record<string, unknown> = {}
): Promise<SimulationResult> {
  return api<SimulationResult>("/executive/simulations", { method: "POST", body: { scenario, params } });
}

export async function listSimulations(): Promise<{ total: number; simulations: SimulationResult[] }> {
  return api<{ total: number; simulations: SimulationResult[] }>("/executive/simulations");
}

export async function getSimulation(simulationId: string): Promise<SimulationResult> {
  return api<SimulationResult>(`/executive/simulations/${simulationId}`);
}

export async function listSimulationScenarios(): Promise<{ scenarios: string[] }> {
  return api<{ scenarios: string[] }>("/executive/simulations/scenarios/list");
}

export async function getDigitalTwin(): Promise<DigitalTwin> {
  return api<DigitalTwin>("/executive/twin");
}

export async function getOrganizationSnapshot(persist = false): Promise<DigitalTwin> {
  return api<DigitalTwin>("/executive/snapshot", { query: { persist } });
}

export async function searchOrganizationMemory(
  query: string,
  limit = 20
): Promise<{ total: number; results: MemoryMatch[] }> {
  return api<{ total: number; results: MemoryMatch[] }>("/executive/twin/search-memory", {
    method: "POST",
    body: { query, limit },
  });
}

export async function getOrganizationTimeline(
  limit = 60
): Promise<{ total: number; entries: ExecutiveTimelineEntry[] }> {
  return api<{ total: number; entries: ExecutiveTimelineEntry[] }>("/executive/timeline", { query: { limit } });
}

export async function getExecutiveTrends(
  period = "weekly"
): Promise<{ period: string; trends: TrendSeries[] }> {
  return api<{ period: string; trends: TrendSeries[] }>("/executive/analytics/trends", { query: { period } });
}

export async function getExecutiveMetrics(): Promise<{ total: number; metrics: ExecutiveMetric[] }> {
  return api<{ total: number; metrics: ExecutiveMetric[] }>("/executive/analytics/metrics");
}

export async function generateExecutiveReport(
  reportType: string,
  departmentId?: string
): Promise<ExecutiveReport> {
  return api<ExecutiveReport>("/executive/reports", {
    method: "POST",
    body: { report_type: reportType, department_id: departmentId },
  });
}

export async function listExecutiveReports(query: {
  report_type?: string;
  limit?: number;
} = {}): Promise<{ total: number; reports: ExecutiveReport[] }> {
  return api<{ total: number; reports: ExecutiveReport[] }>("/executive/reports", { query });
}

export async function listReportTypes(): Promise<{ report_types: string[] }> {
  return api<{ report_types: string[] }>("/executive/reports/types");
}

export async function listStrategicGoals(query: {
  focus?: string;
  status?: string;
} = {}): Promise<{ goals: StrategicGoal[] }> {
  return api<{ goals: StrategicGoal[] }>("/executive/strategy/goals", { query });
}

export async function createStrategicGoal(payload: Record<string, unknown>): Promise<StrategicGoal> {
  return api<StrategicGoal>("/executive/strategy/goals", { method: "POST", body: payload });
}

export async function updateStrategicGoal(
  goalId: string,
  payload: Record<string, unknown>
): Promise<StrategicGoal> {
  return api<StrategicGoal>(`/executive/strategy/goals/${goalId}`, { method: "PATCH", body: payload });
}

export async function getStrategyPlan(horizon = "quarter"): Promise<StrategyPlan> {
  return api<StrategyPlan>("/executive/strategy/plan", { method: "POST", query: { horizon } });
}

export async function askStrategy(question: string): Promise<StrategyAnswer> {
  return api<StrategyAnswer>("/executive/strategy/ask", { method: "POST", body: { question } });
}

// ---------------------------------------------------------------- ai companion

export interface CompanionContext {
  project_id?: string;
  task_id?: string;
  goal_id?: string;
  meeting_id?: string;
}

export interface CompanionStatus {
  available: boolean;
  provider: string;
  mode?: string;
  model?: string;
  message: string;
  grounded: boolean;
  capabilities: string[];
}

export interface CompanionReply {
  answer: string;
  source: "rules" | "llm";
  grounded: Record<string, unknown>;
  intents: string[];
  context: CompanionContext;
  conversation_id?: string;
  message_id?: string;
  tools?: string[];
}

export async function getCompanionStatus(): Promise<CompanionStatus> {
  return api<CompanionStatus>("/ai/companion/status");
}

export async function askCompanion(
  message: string,
  context?: CompanionContext,
  conversationId?: string
): Promise<CompanionReply> {
  return api<CompanionReply>("/ai/companion/ask", {
    method: "POST",
    body: { message, context: context ?? {}, conversation_id: conversationId },
  });
}

export async function* askCompanionStream(
  message: string,
  context?: CompanionContext,
  conversationId?: string
): AsyncGenerator<{ delta?: string; done?: CompanionReply }, void, unknown> {
  const url = `${API_URL}/ai/companion/stream`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, context: context ?? {}, conversation_id: conversationId }),
  });
  if (!response.ok || !response.body) {
    let detail: unknown = null;
    try {
      const data = await response.json();
      detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : "Stream failed");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      for (const line of event.split("\n")) {
        if (line.startsWith("data:")) {
          const payload = JSON.parse(line.slice(5).trim()) as {
            delta?: string;
            done?: CompanionReply;
          };
          if (payload.done) {
            yield { done: payload.done };
            return;
          }
          if (payload.delta) yield { delta: payload.delta };
        }
      }
    }
  }
}

export interface ConversationSummary {
  id: string;
  title: string;
  source: string;
  created_at?: string;
}

export interface ConversationHistory {
  conversation_id: string;
  messages: { id: string; role: string; content: string; source?: string; intents?: string }[];
}

export async function listAiConversations(limit = 20): Promise<{ total: number; conversations: ConversationSummary[] }> {
  return api(`/ai/conversations?limit=${limit}`);
}

export async function getConversationHistory(conversationId: string): Promise<ConversationHistory> {
  return api(`/ai/conversations/${conversationId}`);
}

export async function submitFeedback(payload: {
  message_id?: string;
  content?: string;
  rating?: number;
  helpful?: boolean;
  correction?: string;
}): Promise<{ id: string; status: string }> {
  return api("/ai/feedback", { method: "POST", body: payload });
}

export interface DailyPlan {
  id?: string;
  employee: string;
  plan_type: string;
  overdue?: string[];
  focus: string[];
  tasks: { title: string; status: string; priority: string; due?: string }[];
  meetings: { title: string; start?: string; type: string }[];
  goals: { name: string; progress: number; status: string }[];
}

export async function createPlan(planType: "daily" | "weekly" = "daily"): Promise<DailyPlan> {
  return api("/ai/plan", { method: "POST", body: { plan_type: planType } });
}

export interface RecommendationItem {
  kind: string;
  target_type?: string;
  target_id?: string;
  title: string;
  summary?: string;
  reason?: string;
  score: number;
}

export async function listRecommendations(
  audience: "user" | "organization" = "user"
): Promise<{ total: number; recommendations: RecommendationItem[] }> {
  return api(`/ai/recommendations?audience=${audience}`);
}

export async function universalSearch(query: string, scopes?: string[], limit = 20) {
  return api("/ai/search", { method: "POST", body: { query, scopes, limit } });
}

// ---------------------------------------------------------------------------
// Phase 4 â€” Knowledge Operating System
// ---------------------------------------------------------------------------

export async function listDocuments(query: {
  status?: string;
  category?: string;
  search?: string;
  owner_id?: string;
  project_id?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Document[]> {
  return api<Document[]>("/documents", { query });
}

export async function getDocument(id: string): Promise<Document> {
  return api<Document>(`/documents/${id}`);
}

export async function createDocument(payload: Record<string, unknown>): Promise<Document> {
  return api<Document>("/documents", { method: "POST", body: payload });
}

export async function updateDocument(id: string, payload: Record<string, unknown>): Promise<Document> {
  return api<Document>(`/documents/${id}`, { method: "PATCH", body: payload });
}

export async function deleteDocument(id: string): Promise<Message> {
  return api<Message>(`/documents/${id}`, { method: "DELETE" });
}

export async function publishDocument(id: string): Promise<Document> {
  return api<Document>(`/documents/${id}/publish`, { method: "POST" });
}

export async function archiveDocument(id: string): Promise<Document> {
  return api<Document>(`/documents/${id}/archive`, { method: "POST" });
}

export async function submitDocument(id: string, approverId?: string): Promise<Document> {
  return api<Document>(`/documents/${id}/submit`, { method: "POST", body: { approver_id: approverId } });
}

export async function approveDocument(id: string): Promise<Document> {
  return api<Document>(`/documents/${id}/approve`, { method: "POST" });
}

// ---------------------------------------------------------------- wiki

export async function listWikiPages(query: { space?: string; status?: string; search?: string; limit?: number } = {}): Promise<WikiPage[]> {
  return api<WikiPage[]>("/wiki", { query });
}

export async function getWikiPage(id: string): Promise<WikiPage> {
  return api<WikiPage>(`/wiki/${id}`);
}

export async function createWikiPage(payload: Record<string, unknown>): Promise<WikiPage> {
  return api<WikiPage>("/wiki", { method: "POST", body: payload });
}

export async function updateWikiPage(id: string, payload: Record<string, unknown>): Promise<WikiPage> {
  return api<WikiPage>(`/wiki/${id}`, { method: "PATCH", body: payload });
}

export async function deleteWikiPage(id: string): Promise<Message> {
  return api<Message>(`/wiki/${id}`, { method: "DELETE" });
}

export async function publishWikiPage(id: string): Promise<WikiPage> {
  return api<WikiPage>(`/wiki/${id}/publish`, { method: "POST" });
}

export async function moveWikiPage(id: string, parentId: string | null): Promise<WikiPage> {
  return api<WikiPage>(`/wiki/${id}/move`, { method: "POST", body: { parent_id: parentId } });
}

export async function getWikiTree(): Promise<WikiTreeNode[]> {
  return api<WikiTreeNode[]>("/wiki/tree");
}

export async function getWikiChildren(id: string): Promise<WikiPage[]> {
  return api<WikiPage[]>(`/wiki/${id}/children`);
}

// ---------------------------------------------------------------- policies

export async function listPolicies(query: { category?: string; status?: string; search?: string; limit?: number } = {}): Promise<Policy[]> {
  return api<Policy[]>("/policies", { query });
}

export async function getPolicy(id: string): Promise<Policy> {
  return api<Policy>(`/policies/${id}`);
}

export async function createPolicy(payload: Record<string, unknown>): Promise<Policy> {
  return api<Policy>("/policies", { method: "POST", body: payload });
}

export async function updatePolicy(id: string, payload: Record<string, unknown>): Promise<Policy> {
  return api<Policy>(`/policies/${id}`, { method: "PATCH", body: payload });
}

export async function deletePolicy(id: string): Promise<Message> {
  return api<Message>(`/policies/${id}`, { method: "DELETE" });
}

export async function submitPolicy(id: string, approverId?: string): Promise<Policy> {
  return api<Policy>(`/policies/${id}/submit`, { method: "POST", body: { approver_id: approverId } });
}

export async function approvePolicy(id: string, note?: string): Promise<Policy> {
  return api<Policy>(`/policies/${id}/approve`, { method: "POST", body: { note } });
}

export async function rejectPolicy(id: string, note?: string): Promise<Policy> {
  return api<Policy>(`/policies/${id}/reject`, { method: "POST", body: { note } });
}

export async function listOverduePolicies(): Promise<Policy[]> {
  return api<Policy[]>("/policies/overdue");
}

// ---------------------------------------------------------------- sops

export async function listSops(query: { category?: string; status?: string; search?: string; limit?: number } = {}): Promise<SOP[]> {
  return api<SOP[]>("/sops", { query });
}

export async function getSop(id: string): Promise<SOP> {
  return api<SOP>(`/sops/${id}`);
}

export async function createSop(payload: Record<string, unknown>): Promise<SOP> {
  return api<SOP>("/sops", { method: "POST", body: payload });
}

export async function updateSop(id: string, payload: Record<string, unknown>): Promise<SOP> {
  return api<SOP>(`/sops/${id}`, { method: "PATCH", body: payload });
}

export async function deleteSop(id: string): Promise<Message> {
  return api<Message>(`/sops/${id}`, { method: "DELETE" });
}

export async function publishSop(id: string): Promise<SOP> {
  return api<SOP>(`/sops/${id}/publish`, { method: "POST" });
}

// ---------------------------------------------------------------- templates

export async function listTemplates(query: { kind?: string; status?: string; search?: string; limit?: number } = {}): Promise<Template[]> {
  return api<Template[]>("/templates", { query });
}

export async function getTemplate(id: string): Promise<Template> {
  return api<Template>(`/templates/${id}`);
}

export async function createTemplate(payload: Record<string, unknown>): Promise<Template> {
  return api<Template>("/templates", { method: "POST", body: payload });
}

export async function updateTemplate(id: string, payload: Record<string, unknown>): Promise<Template> {
  return api<Template>(`/templates/${id}`, { method: "PATCH", body: payload });
}

export async function deleteTemplate(id: string): Promise<Message> {
  return api<Message>(`/templates/${id}`, { method: "DELETE" });
}

export async function publishTemplate(id: string): Promise<Template> {
  return api<Template>(`/templates/${id}/publish`, { method: "POST" });
}

export async function useTemplate(id: string): Promise<Template> {
  return api<Template>(`/templates/${id}/use`, { method: "POST" });
}

export async function listMostUsedTemplates(): Promise<Template[]> {
  return api<Template[]>("/templates/most-used");
}

// ---------------------------------------------------------------- decisions

export async function listDecisions(query: { status?: string; project_id?: string; search?: string; limit?: number } = {}): Promise<Decision[]> {
  return api<Decision[]>("/decisions", { query });
}

export async function getDecision(id: string): Promise<Decision> {
  return api<Decision>(`/decisions/${id}`);
}

export async function createDecision(payload: Record<string, unknown>): Promise<Decision> {
  return api<Decision>("/decisions", { method: "POST", body: payload });
}

export async function updateDecision(id: string, payload: Record<string, unknown>): Promise<Decision> {
  return api<Decision>(`/decisions/${id}`, { method: "PATCH", body: payload });
}

export async function deleteDecision(id: string): Promise<Message> {
  return api<Message>(`/decisions/${id}`, { method: "DELETE" });
}

export async function chooseDecisionOption(id: string, optionId: string, reason?: string): Promise<Decision> {
  return api<Decision>(`/decisions/${id}/choose`, { method: "POST", body: { option_id: optionId, reason } });
}

export async function transitionDecision(id: string, status: string): Promise<Decision> {
  return api<Decision>(`/decisions/${id}/status`, { method: "POST", body: { status } });
}

export async function executeDecisionAction(id: string, actionIndex: number): Promise<{ decision: Decision; task: Task }> {
  return api<{ decision: Decision; task: Task }>(`/decisions/${id}/actions/${actionIndex}/execute`, { method: "POST" });
}

export async function listDecisionTasks(id: string): Promise<Task[]> {
  return api<Task[]>(`/decisions/${id}/tasks`);
}

// ---------------------------------------------------------------- hub

export async function knowledgeSearch(query: {
  q: string;
  mode?: "keyword" | "semantic" | "hybrid";
  kind?: string;
  status?: string;
  project_id?: string;
  author_id?: string;
  tags?: string;
  limit?: number;
  offset?: number;
}): Promise<KnowledgeSearchResponse> {
  return api<KnowledgeSearchResponse>("/knowledge/search", { query });
}

export async function getKnowledgeGraph(query: { kind?: string; focus?: string; depth?: number; limit?: number } = {}): Promise<KnowledgeGraph> {
  return api<KnowledgeGraph>("/knowledge/graph", { query });
}

export async function getKnowledgeAnalytics(): Promise<KnowledgeAnalytics> {
  return api<KnowledgeAnalytics>("/knowledge/analytics");
}

export async function getKnowledgeRecommendations(limit = 10): Promise<KnowledgeRecommendation[]> {
  return api<KnowledgeRecommendation[]>("/knowledge/recommendations", { query: { limit } });
}

export async function getKnowledgeExperts(topic?: string): Promise<KnowledgeExpert[]> {
  return api<KnowledgeExpert[]>("/knowledge/experts", { query: { topic } });
}

export async function getStaleKnowledge(days = 180): Promise<KnowledgeRecentItem[]> {
  return api<KnowledgeRecentItem[]>("/knowledge/stale", { query: { days } });
}

export async function getRecentKnowledge(limit = 10): Promise<KnowledgeRecentItem[]> {
  return api<KnowledgeRecentItem[]>("/knowledge/recent", { query: { limit } });
}

export async function getMyKnowledgeFavorites(): Promise<KnowledgeRecentItem[]> {
  return api<KnowledgeRecentItem[]>("/knowledge/favorites");
}

export async function listKnowledgeCategories(): Promise<KnowledgeCategory[]> {
  return api<KnowledgeCategory[]>("/knowledge/categories");
}

export async function createKnowledgeCategory(payload: { name: string; description?: string; color?: string }): Promise<KnowledgeCategory> {
  return api<KnowledgeCategory>("/knowledge/categories", { method: "POST", body: payload });
}

export async function listKnowledgeTags(): Promise<KnowledgeTag[]> {
  return api<KnowledgeTag[]>("/knowledge/tags");
}

export async function listKnowledgeVersions(kind: string, entityId: string): Promise<KnowledgeVersion[]> {
  return api<KnowledgeVersion[]>(`/knowledge/${kind}/${entityId}/versions`);
}

export async function getKnowledgeVersion(kind: string, entityId: string, version: number): Promise<KnowledgeVersion> {
  return api<KnowledgeVersion>(`/knowledge/${kind}/${entityId}/versions/${version}`);
}

export async function restoreKnowledgeVersion(kind: string, entityId: string, version: number): Promise<Document> {
  return api<Document>(`/knowledge/${kind}/${entityId}/versions/${version}/restore`, { method: "POST" });
}

export async function listKnowledgeComments(kind: string, entityId: string): Promise<KnowledgeComment[]> {
  return api<KnowledgeComment[]>(`/knowledge/${kind}/${entityId}/comments`);
}

export async function addKnowledgeComment(kind: string, entityId: string, content: string): Promise<KnowledgeComment> {
  return api<KnowledgeComment>(`/knowledge/${kind}/${entityId}/comments`, { method: "POST", body: { content } });
}

export async function updateKnowledgeComment(kind: string, entityId: string, commentId: string, content: string): Promise<KnowledgeComment> {
  return api<KnowledgeComment>(`/knowledge/${kind}/${entityId}/comments/${commentId}`, { method: "PATCH", body: { content } });
}

export async function deleteKnowledgeComment(kind: string, entityId: string, commentId: string): Promise<Message> {
  return api<Message>(`/knowledge/${kind}/${entityId}/comments/${commentId}`, { method: "DELETE" });
}

export async function toggleWatch(kind: string, entityId: string): Promise<{ watching: boolean }> {
  return api<{ watching: boolean }>(`/knowledge/${kind}/${entityId}/watch`, { method: "POST" });
}

export async function listWatchers(kind: string, entityId: string): Promise<KnowledgeWatcher[]> {
  return api<KnowledgeWatcher[]>(`/knowledge/${kind}/${entityId}/watchers`);
}

export async function toggleFavorite(kind: string, entityId: string): Promise<{ favorited: boolean }> {
  return api<{ favorited: boolean }>(`/knowledge/${kind}/${entityId}/favorite`, { method: "POST" });
}

export async function touchPresence(kind: string, entityId: string): Promise<{ presence: string }> {
  return api<{ presence: string }>(`/knowledge/${kind}/${entityId}/presence`, { method: "POST" });
}

export async function listPresence(kind: string, entityId: string): Promise<KnowledgePresence[]> {
  return api<KnowledgePresence[]>(`/knowledge/${kind}/${entityId}/presence`);
}

export async function listKnowledgeRelations(kind: string, entityId: string): Promise<KnowledgeRelation[]> {
  return api<KnowledgeRelation[]>(`/knowledge/${kind}/${entityId}/relations`);
}

export async function addKnowledgeRelation(kind: string, entityId: string, payload: { target_type: string; target_id: string; relation_type?: string }): Promise<KnowledgeRelation> {
  return api<KnowledgeRelation>(`/knowledge/${kind}/${entityId}/relations`, { method: "POST", body: payload });
}

export async function removeKnowledgeRelation(kind: string, entityId: string, relationId: string): Promise<Message> {
  return api<Message>(`/knowledge/${kind}/${entityId}/relations/${relationId}`, { method: "DELETE" });
}

export async function submitKnowledge(kind: string, entityId: string, approverId?: string): Promise<{ status: string; entity_id: string; kind: string }> {
  return api<{ status: string; entity_id: string; kind: string }>(`/knowledge/${kind}/${entityId}/submit`, {
    method: "POST",
    body: { approver_id: approverId },
  });
}

// ---------------------------------------------------------------------------
// Phase 5 â€” Communication & Community
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------- communities

export async function listCommunities(query: {
  type?: string;
  search?: string;
  mine_only?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<Community[]> {
  return api<Community[]>("/communities", { query: query as Record<string, string | number | boolean | null | undefined> });
}

export async function getCommunity(id: string): Promise<Community> {
  return api<Community>(`/communities/${id}`);
}

export async function createCommunity(payload: {
  name: string;
  description?: string;
  type?: string;
  visibility?: string;
  icon?: string;
  banner?: string;
}): Promise<Community> {
  return api<Community>("/communities", { method: "POST", body: payload });
}

export async function updateCommunity(id: string, payload: Record<string, unknown>): Promise<Community> {
  return api<Community>(`/communities/${id}`, { method: "PATCH", body: payload });
}

export async function deleteCommunity(id: string): Promise<Message> {
  return api<Message>(`/communities/${id}`, { method: "DELETE" });
}

export async function joinCommunity(id: string): Promise<Community> {
  return api<Community>(`/communities/${id}/join`, { method: "POST" });
}

export async function leaveCommunity(id: string): Promise<Message> {
  return api<Message>(`/communities/${id}/leave`, { method: "POST" });
}

export async function setCommunityRole(id: string, employeeId: string, role: "owner" | "moderator" | "member"): Promise<{ employee_id: string; role: string }> {
  return api<{ employee_id: string; role: string }>(`/communities/${id}/role`, {
    method: "POST",
    body: { employee_id: employeeId, role },
  });
}

export async function listCommunityMembers(id: string, limit = 100, offset = 0): Promise<CommunityMember[]> {
  return api<CommunityMember[]>(`/communities/${id}/members`, { query: { limit, offset } });
}

export async function getCommunityAnalytics(): Promise<CommunityAnalytics> {
  return api<CommunityAnalytics>("/communities/analytics");
}

// ---------------------------------------------------------------- posts

export async function listFeed(query: {
  community_id?: string;
  mine_only?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<Post[]> {
  return api<Post[]>("/posts/feed", { query: query as Record<string, string | number | boolean | null | undefined> });
}

export async function getPost(id: string): Promise<Post> {
  return api<Post>(`/posts/${id}`);
}

export async function createPost(communityId: string, payload: {
  title?: string;
  content?: string;
  attachments?: unknown[];
  visibility?: string;
  status?: string;
  pinned?: boolean;
  scheduled_at?: string;
}): Promise<Post> {
  return api<Post>("/posts", { method: "POST", query: { community_id: communityId }, body: payload });
}

export async function updatePost(id: string, payload: Record<string, unknown>): Promise<Post> {
  return api<Post>(`/posts/${id}`, { method: "PATCH", body: payload });
}

export async function deletePost(id: string): Promise<Message> {
  return api<Message>(`/posts/${id}`, { method: "DELETE" });
}

export async function togglePostPin(id: string, pinned = true): Promise<{ pinned: boolean }> {
  return api<{ pinned: boolean }>(`/posts/${id}/pin`, { method: "POST", query: { pinned } });
}

export async function togglePostBookmark(id: string): Promise<{ bookmarked: boolean; bookmark_count: number }> {
  return api<{ bookmarked: boolean; bookmark_count: number }>(`/posts/${id}/bookmark`, { method: "POST" });
}

export async function reactToPost(id: string, emoji: string): Promise<{ reacted: boolean; emoji: string }> {
  return api<{ reacted: boolean; emoji: string }>(`/posts/${id}/reactions`, { method: "POST", body: { emoji } });
}

export async function listPostReactions(id: string): Promise<{ emoji: string; count: number }[]> {
  return api<{ emoji: string; count: number }[]>(`/posts/${id}/reactions`);
}

export async function listPostComments(id: string, limit = 200, offset = 0): Promise<PostComment[]> {
  return api<PostComment[]>(`/posts/${id}/comments`, { query: { limit, offset } });
}

export async function addPostComment(postId: string, content: string, parentId?: string, isResolution = false): Promise<PostComment> {
  return api<PostComment>(`/posts/${postId}/comments`, {
    method: "POST",
    body: { content, parent_id: parentId, is_resolution: isResolution },
  });
}

export async function updatePostComment(postId: string, commentId: string, payload: Record<string, unknown>): Promise<PostComment> {
  return api<PostComment>(`/posts/${postId}/comments/${commentId}`, { method: "PATCH", body: payload });
}

export async function deletePostComment(postId: string, commentId: string): Promise<Message> {
  return api<Message>(`/posts/${postId}/comments/${commentId}`, { method: "DELETE" });
}

export async function reactToComment(postId: string, commentId: string, emoji: string): Promise<{ reacted: boolean; emoji: string }> {
  return api<{ reacted: boolean; emoji: string }>(`/posts/${postId}/comments/${commentId}/reactions`, {
    method: "POST",
    body: { emoji },
  });
}

// ---------------------------------------------------------------- announcements

export async function listAnnouncements(query: {
  status?: string;
  type?: string;
  priority?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Announcement[]> {
  return api<Announcement[]>("/announcements", { query });
}

export async function getAnnouncement(id: string): Promise<Announcement> {
  return api<Announcement>(`/announcements/${id}`);
}

export async function createAnnouncement(payload: {
  title: string;
  body?: string;
  type?: string;
  priority?: string;
  status?: string;
  department_id?: string;
  team_id?: string;
  starts_at?: string;
  ends_at?: string;
  pinned?: boolean;
  acknowledge_required?: boolean;
  attachments?: unknown[];
}): Promise<Announcement> {
  return api<Announcement>("/announcements", { method: "POST", body: payload });
}

export async function updateAnnouncement(id: string, payload: Record<string, unknown>): Promise<Announcement> {
  return api<Announcement>(`/announcements/${id}`, { method: "PATCH", body: payload });
}

export async function deleteAnnouncement(id: string): Promise<Message> {
  return api<Message>(`/announcements/${id}`, { method: "DELETE" });
}

export async function publishAnnouncement(id: string): Promise<Announcement> {
  return api<Announcement>(`/announcements/${id}/publish`, { method: "POST" });
}

export async function markAnnouncementRead(id: string): Promise<{ read: boolean; read_at: string }> {
  return api<{ read: boolean; read_at: string }>(`/announcements/${id}/read`, { method: "POST" });
}

export async function acknowledgeAnnouncement(id: string): Promise<{ acknowledged: boolean; acknowledged_at: string }> {
  return api<{ acknowledged: boolean; acknowledged_at: string }>(`/announcements/${id}/acknowledge`, { method: "POST" });
}

export async function listAnnouncementReceipts(id: string): Promise<AnnouncementReceipt[]> {
  return api<AnnouncementReceipt[]>(`/announcements/${id}/receipts`);
}

// ---------------------------------------------------------------- forums

export async function listForumCategories(): Promise<{ category: string; thread_count: number; last_activity: string }[]> {
  return api<{ category: string; thread_count: number; last_activity: string }[]>("/forums/categories");
}

export async function listForumThreads(query: {
  category?: string;
  status?: string;
  search?: string;
  tag?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ForumThread[]> {
  return api<ForumThread[]>("/forums", { query });
}

export async function getForumThread(id: string): Promise<ForumThread> {
  return api<ForumThread>(`/forums/${id}`);
}

export async function createForumThread(payload: {
  category: string;
  title: string;
  content?: string;
  tags?: string[];
}): Promise<ForumThread> {
  return api<ForumThread>("/forums", { method: "POST", body: payload });
}

export async function updateForumThread(id: string, payload: Record<string, unknown>): Promise<ForumThread> {
  return api<ForumThread>(`/forums/${id}`, { method: "PATCH", body: payload });
}

export async function deleteForumThread(id: string): Promise<Message> {
  return api<Message>(`/forums/${id}`, { method: "DELETE" });
}

export async function recordThreadView(id: string): Promise<{ viewed: boolean }> {
  return api<{ viewed: boolean }>(`/forums/${id}/view`, { method: "POST" });
}

export async function toggleThreadPin(id: string, pinned = true): Promise<{ is_pinned: boolean }> {
  return api<{ is_pinned: boolean }>(`/forums/${id}/pin`, { method: "POST", query: { pinned } });
}

export async function voteThread(id: string, value: number): Promise<{ voted: number | null; vote_count: number }> {
  return api<{ voted: number | null; vote_count: number }>(`/forums/${id}/vote`, { method: "POST", body: { value } });
}

export async function acceptThreadReply(id: string, replyId?: string): Promise<{ accepted_reply_id: string | null; is_resolved: boolean }> {
  return api<{ accepted_reply_id: string | null; is_resolved: boolean }>(`/forums/${id}/accept`, {
    method: "POST",
    query: { reply_id: replyId },
  });
}

export async function listForumReplies(threadId: string, limit = 300, offset = 0): Promise<ForumReply[]> {
  return api<ForumReply[]>(`/forums/${threadId}/replies`, { query: { limit, offset } });
}

export async function addForumReply(threadId: string, content: string, parentId?: string): Promise<ForumReply> {
  return api<ForumReply>(`/forums/${threadId}/replies`, {
    method: "POST",
    body: { content, parent_id: parentId },
  });
}

export async function updateForumReply(threadId: string, replyId: string, content: string): Promise<ForumReply> {
  return api<ForumReply>(`/forums/${threadId}/replies/${replyId}`, { method: "PATCH", body: { content } });
}

export async function deleteForumReply(threadId: string, replyId: string): Promise<Message> {
  return api<Message>(`/forums/${threadId}/replies/${replyId}`, { method: "DELETE" });
}

export async function voteForumReply(threadId: string, replyId: string, value: number): Promise<{ voted: number | null; vote_count: number }> {
  return api<{ voted: number | null; vote_count: number }>(`/forums/${threadId}/replies/${replyId}/vote`, {
    method: "POST",
    body: { value },
  });
}

// ---------------------------------------------------------------- recognition

export async function listRecognition(query: {
  employee_id?: string;
  category?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Recognition[]> {
  return api<Recognition[]>("/recognition", { query });
}

export async function giveRecognition(payload: {
  recipient_id: string;
  category: string;
  message?: string;
  badge_code?: string;
  public?: boolean;
}): Promise<Recognition> {
  return api<Recognition>("/recognition", { method: "POST", body: payload });
}

export async function deleteRecognition(id: string): Promise<Message> {
  return api<Message>(`/recognition/${id}`, { method: "DELETE" });
}

export async function getRecognitionStats(): Promise<{
  total: number;
  this_month: number;
  categories: { category: string; count: number }[];
  top_recipients: { employee_id: string; count: number; employee_name: string }[];
  top_givers: { employee_id: string; count: number; employee_name: string }[];
}> {
  return api("/recognition/stats");
}

export async function getMyBadges(): Promise<EmployeeBadge[]> {
  return api<EmployeeBadge[]>("/recognition/badges");
}

export async function getAllBadges(): Promise<Badge[]> {
  return api<Badge[]>("/recognition/badges/all");
}

export async function getRecognitionLeaderboard(limit = 20): Promise<{ employee_id: string; badge_count: number; employee_name: string }[]> {
  return api<{ employee_id: string; badge_count: number; employee_name: string }[]>("/recognition/leaderboard", { query: { limit } });
}

// ---------------------------------------------------------------- innovation

export async function listIdeas(query: {
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Idea[]> {
  return api<Idea[]>("/innovation", { query });
}

export async function getIdea(id: string): Promise<Idea> {
  return api<Idea>(`/innovation/${id}`);
}

export async function createIdea(payload: {
  title: string;
  description?: string;
  problem?: string;
  solution?: string;
  impact?: string;
  tags?: string[];
}): Promise<Idea> {
  return api<Idea>("/innovation", { method: "POST", body: payload });
}

export async function updateIdea(id: string, payload: Record<string, unknown>): Promise<Idea> {
  return api<Idea>(`/innovation/${id}`, { method: "PATCH", body: payload });
}

export async function deleteIdea(id: string): Promise<Message> {
  return api<Message>(`/innovation/${id}`, { method: "DELETE" });
}

export async function voteIdea(id: string): Promise<{ voted: boolean; vote_count: number }> {
  return api<{ voted: boolean; vote_count: number }>(`/innovation/${id}/vote`, { method: "POST" });
}

export async function setIdeaStatus(id: string, status: string, feedback?: string): Promise<Idea> {
  return api<Idea>(`/innovation/${id}/status`, { method: "PATCH", body: { status, feedback } });
}

export async function promoteIdea(id: string, projectId?: string): Promise<Idea> {
  return api<Idea>(`/innovation/${id}/promote`, { method: "POST", body: { project_id: projectId } });
}

export async function getInnovationStats(): Promise<{ total: number; by_status: { status: string; count: number }[] }> {
  return api("/innovation/stats");
}

// ---------------------------------------------------------------- polls

export async function listPolls(query: {
  status?: string;
  community_id?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Poll[]> {
  return api<Poll[]>("/polls", { query });
}

export async function getPoll(id: string): Promise<Poll> {
  return api<Poll>(`/polls/${id}`);
}

export async function createPoll(payload: {
  title: string;
  question?: string;
  description?: string;
  community_id?: string;
  anonymous?: boolean;
  multiple_choice?: boolean;
  status?: string;
  ends_at?: string;
  options: { text: string; sort_order?: number }[];
}): Promise<Poll> {
  return api<Poll>("/polls", { method: "POST", body: payload });
}

export async function updatePoll(id: string, payload: Record<string, unknown>): Promise<Poll> {
  return api<Poll>(`/polls/${id}`, { method: "PATCH", body: payload });
}

export async function deletePoll(id: string): Promise<Message> {
  return api<Message>(`/polls/${id}`, { method: "DELETE" });
}

export async function votePoll(id: string, optionIds: string[]): Promise<{ voted: boolean; vote_count: number }> {
  return api<{ voted: boolean; vote_count: number }>(`/polls/${id}/vote`, { method: "POST", body: { option_ids: optionIds } });
}

export async function getPollResults(id: string): Promise<PollResult> {
  return api<PollResult>(`/polls/${id}/results`);
}

// ---------------------------------------------------------------- community events

export async function listCommunityEvents(query: {
  type?: string;
  upcoming?: boolean;
  community_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<CommunityEvent[]> {
  return api<CommunityEvent[]>("/community-events", { query });
}

export async function getCommunityEvent(id: string): Promise<CommunityEvent> {
  return api<CommunityEvent>(`/community-events/${id}`);
}

export async function createCommunityEvent(payload: {
  title: string;
  description?: string;
  type?: string;
  community_id?: string;
  starts_at: string;
  ends_at?: string;
  location?: string;
  virtual_url?: string;
  capacity?: number;
  status?: string;
  registration_deadline?: string;
  team_based?: boolean;
}): Promise<CommunityEvent> {
  return api<CommunityEvent>("/community-events", { method: "POST", body: payload });
}

export async function updateCommunityEvent(id: string, payload: Record<string, unknown>): Promise<CommunityEvent> {
  return api<CommunityEvent>(`/community-events/${id}`, { method: "PATCH", body: payload });
}

export async function deleteCommunityEvent(id: string): Promise<Message> {
  return api<Message>(`/community-events/${id}`, { method: "DELETE" });
}

export async function registerForEvent(id: string, teamName?: string, role = "participant"): Promise<{ registered: boolean; registration_count: number }> {
  return api<{ registered: boolean; registration_count: number }>(`/community-events/${id}/register`, {
    method: "POST",
    body: { team_name: teamName, role },
  });
}

export async function listEventRegistrations(id: string): Promise<EventRegistration[]> {
  return api<EventRegistration[]>(`/community-events/${id}/registrations`);
}

export async function getCommunityEventStats(): Promise<{ total: number; upcoming: number; registrations: number }> {
  return api("/community-events/stats");
}

// ---------------------------------------------------------------- messaging

export async function listConversations(): Promise<Conversation[]> {
  return api<Conversation[]>("/conversations");
}

export async function createConversation(payload: {
  type?: string;
  title?: string;
  member_ids?: string[];
  channel_kind?: string;
  channel_key?: string;
  community_id?: string;
}): Promise<Conversation> {
  return api<Conversation>("/conversations", { method: "POST", body: payload });
}

export async function openDm(employeeId: string): Promise<Conversation> {
  return api<Conversation>(`/dms/${employeeId}`, { method: "POST" });
}

export async function getConversation(id: string): Promise<Conversation> {
  return api<Conversation>(`/conversations/${id}`);
}

export async function archiveConversation(id: string): Promise<Message> {
  return api<Message>(`/conversations/${id}/archive`, { method: "POST" });
}

export async function listConversationMembers(id: string): Promise<ConversationMember[]> {
  return api<ConversationMember[]>(`/conversations/${id}/members`);
}

export async function addConversationMember(id: string, employeeId: string): Promise<{ employee_id: string; role: string }> {
  return api<{ employee_id: string; role: string }>(`/conversations/${id}/members`, {
    method: "POST",
    body: { employee_id: employeeId },
  });
}

export async function removeConversationMember(id: string, employeeId: string): Promise<Message> {
  return api<Message>(`/conversations/${id}/members/${employeeId}`, { method: "DELETE" });
}

export async function markConversationRead(id: string): Promise<{ read: boolean }> {
  return api<{ read: boolean }>(`/conversations/${id}/read`, { method: "POST" });
}

export async function listMessages(conversationId: string, limit = 100, offset = 0): Promise<ChatMessage[]> {
  return api<ChatMessage[]>(`/conversations/${conversationId}/messages`, { query: { limit, offset } });
}

export async function sendMessage(conversationId: string, payload: {
  content?: string;
  reply_to?: string;
  attachments?: unknown[];
  mentions?: string[];
}): Promise<ChatMessage> {
  return api<ChatMessage>(`/conversations/${conversationId}/messages`, { method: "POST", body: payload });
}

export async function listPinnedMessages(conversationId: string): Promise<ChatMessage[]> {
  return api<ChatMessage[]>(`/conversations/${conversationId}/pinned`);
}

export async function listMyMentions(limit = 50): Promise<ChatMessage[]> {
  return api<ChatMessage[]>("/mentions", { query: { limit } });
}

export async function getMessage(id: string): Promise<ChatMessage> {
  return api<ChatMessage>(`/messages/${id}`);
}

export async function editMessage(id: string, content: string): Promise<ChatMessage> {
  return api<ChatMessage>(`/messages/${id}`, { method: "PATCH", body: { content } });
}

export async function deleteMessage(id: string): Promise<Message> {
  return api<Message>(`/messages/${id}`, { method: "DELETE" });
}

export async function reactToMessage(id: string, emoji: string): Promise<{ reacted: boolean; reaction_count: number }> {
  return api<{ reacted: boolean; reaction_count: number }>(`/messages/${id}/reactions`, { method: "POST", body: { emoji } });
}

export async function listMessageReactions(id: string): Promise<{ emoji: string; count: number }[]> {
  return api<{ emoji: string; count: number }[]>(`/messages/${id}/reactions`);
}

export async function markMessageRead(id: string): Promise<{ read: boolean }> {
  return api<{ read: boolean }>(`/messages/${id}/read`, { method: "POST" });
}

export async function toggleMessagePin(id: string): Promise<{ pinned: boolean }> {
  return api<{ pinned: boolean }>(`/messages/${id}/pin`, { method: "POST" });
}

// ---------------------------------------------------------------- background intelligence (Phase 9)

export interface IntelligenceEvent {
  id: string;
  name: string;
  organization_id?: string;
  actor_id?: string;
  payload?: Record<string, unknown>;
  occurred_at?: string;
  processed_at?: string | null;
}

export interface IntelligenceJobs {
  queued: number;
  running: number;
  done: number;
  retry: number;
  failed: number;
}

export interface GraphStats {
  edges: number;
  active_edges?: number;
  employees?: number;
  [key: string]: unknown;
}

export interface GraphEdge {
  id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  relation: string;
  weight: number;
  evidence?: string;
  active: boolean;
  source_name?: string;
  target_name?: string;
  created_at?: string;
}

export interface GraphPathStep {
  edge_id: string;
  relation: string;
  source_id: string;
  target_id: string;
  [key: string]: unknown;
}

export interface ExpertiseLeaderEntry {
  employee_id: string;
  name: string;
  designation?: string;
  department_id?: string;
  expertise_score: number;
  top_skills: { skill_id: string; skill_name: string; score: number }[];
}

export interface ExpertiseHistoryEntry {
  id: string;
  skill_name: string;
  before: number;
  after: number;
  delta: number;
  source_event: string;
  reason?: string;
  created_at?: string;
}

export interface KnowledgeInsight {
  id: string;
  kind: "outdated" | "duplicate" | "unused" | "missing" | "conflict" | "gap";
  entity_type?: string;
  entity_id?: string;
  related_type?: string;
  related_id?: string;
  title: string;
  detail?: string;
  recommendation?: string;
  confidence: number;
  status: "open" | "accepted" | "dismissed";
  created_at?: string;
}

export interface SearchInsight {
  id: string;
  kind: string;
  query?: string;
  count: number;
  status: string;
  created_at?: string;
}

export interface SearchStats {
  total_searches: number;
  failed: number;
  success_rate: number;
  [key: string]: unknown;
}

export interface BurnoutSignal {
  id: string;
  employee_id: string;
  employee_name?: string;
  score: number;
  level: "low" | "moderate" | "elevated" | "high";
  signals_json?: Record<string, unknown>;
  suggestions?: string[];
  status: "open" | "acknowledged" | "resolved";
  period_start?: string;
  created_at?: string;
}

export interface DuplicateDetection {
  id: string;
  kind: string;
  entity_type_a?: string;
  entity_id_a?: string;
  title_a?: string;
  entity_type_b?: string;
  entity_id_b?: string;
  title_b?: string;
  similarity: number;
  status: "open" | "confirmed" | "dismissed";
  created_at?: string;
}

export interface PatternDetection {
  id: string;
  pattern_type: string;
  key?: string;
  title: string;
  detail?: string;
  count: number;
  first_seen?: string;
  last_seen?: string;
  status: "open" | "acknowledged" | "dismissed";
  created_at?: string;
}

export interface WorkflowInsight {
  id: string;
  insight_type: string;
  entity_type?: string;
  entity_id?: string;
  title: string;
  detail?: string;
  severity: string;
  recommendation?: string;
  status: "open" | "accepted" | "dismissed";
  created_at?: string;
}

export interface LearningLesson {
  id: string;
  event_type: string;
  title: string;
  detail?: string;
  lesson?: string;
  entity_type?: string;
  entity_id?: string;
  tags?: string[];
  created_at?: string;
}

export interface LearningSummary {
  total: number;
  by_type: Record<string, number>;
}

export interface CollaborationMetrics {
  period_start: string;
  department_pairs: { a: string; b: string; interactions: number }[];
  department_activity: Record<string, number>;
  silos: { employee_id: string; name?: string; department_id?: string }[];
  [key: string]: unknown;
}

export interface BriefSection {
  title: string;
  items: string[];
  severity: "critical" | "warning" | "info" | "neutral";
}

export interface DailyBrief {
  id: string;
  brief_type: "executive" | "employee";
  recipient_id?: string;
  recipient_name?: string;
  brief_date: string;
  sections: BriefSection[];
  created_at?: string;
}

export interface RecommendationItem {
  id: string;
  kind: string;
  title: string;
  body?: string;
  entity_type?: string;
  entity_id?: string;
  score: number;
  reasons: string[];
  status: "active" | "accepted" | "dismissed";
  created_at?: string;
}

export interface WorkerInfo {
  name: string;
  interval_seconds?: number;
  run_on_demand: boolean;
}

export interface IntelligenceOverview {
  graph: GraphStats;
  search: SearchStats;
  learning: LearningSummary;
  jobs: IntelligenceJobs;
  burnout: { count: number; latest: BurnoutSignal[] };
  knowledge: { count: number; latest: KnowledgeInsight[] };
  duplicates: { count: number; latest: DuplicateDetection[] };
  patterns: { count: number; latest: PatternDetection[] };
  workflow: { count: number; latest: WorkflowInsight[] };
  risks?: { count: number; latest: InsightRisk[] };
  autonomous_notifications?: { count: number };
}

export interface InsightRisk {
  id: string;
  kind: string;
  title: string;
  description?: string | null;
  probability: number;
  impact: number;
  score: number;
  level: string;
  subject_type?: string | null;
  subject_id?: string | null;
  subject_name?: string | null;
  status: string;
  created_at?: string | null;
}

export interface AutonomousNotification {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  priority: string;
  link?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  recipient_id?: string | null;
  created_at?: string | null;
}

export interface InsightsFeed {
  risks: InsightRisk[];
  knowledge: KnowledgeInsight[];
  burnout: BurnoutSignal[];
  duplicates: DuplicateDetection[];
  patterns: PatternDetection[];
  workflow: WorkflowInsight[];
  search: unknown[];
  counts: {
    risks: number;
    knowledge: number;
    burnout: number;
    duplicates: number;
    patterns: number;
    workflow: number;
    search: number;
  };
}

export async function getIntelligenceOverview(): Promise<IntelligenceOverview> {
  return api<IntelligenceOverview>("/intelligence/overview");
}

export async function listIntelligenceEvents(limit = 50, processed?: boolean): Promise<IntelligenceEvent[]> {
  return api<IntelligenceEvent[]>("/intelligence/events", { query: { limit, processed } });
}

export async function getIntelligenceEventStats(): Promise<IntelligenceJobs> {
  return api<IntelligenceJobs>("/intelligence/events/stats");
}

export async function processPendingEvents(limit = 50): Promise<{ processed: number }> {
  return api<{ processed: number }>("/intelligence/events/process", { method: "POST", query: { limit } });
}

export async function listIntelligenceJobs(limit = 50, status?: string): Promise<unknown[]> {
  return api<unknown[]>("/intelligence/jobs", { query: { limit, status } });
}

export async function listWorkers(): Promise<WorkerInfo[]> {
  return api<WorkerInfo[]>("/intelligence/workers");
}

export async function runWorkerOnDemand(name: string): Promise<{ worker: string; processed: number }> {
  return api<{ worker: string; processed: number }>(`/intelligence/workers/${name}/run`, { method: "POST" });
}

export async function getExpertiseLeaderboard(limit = 20): Promise<ExpertiseLeaderEntry[]> {
  return api<ExpertiseLeaderEntry[]>("/intelligence/expertise/leaderboard", { query: { limit } });
}

export async function getExpertiseHistory(employeeId: string, limit = 50): Promise<ExpertiseHistoryEntry[]> {
  return api<ExpertiseHistoryEntry[]>(`/intelligence/expertise/${employeeId}/history`, { query: { limit } });
}

export async function getGraphStats(): Promise<GraphStats> {
  return api<GraphStats>("/intelligence/graph");
}

export async function listGraphEdges(params: { relation?: string; entity_type?: string; limit?: number } = {}): Promise<GraphEdge[]> {
  return api<GraphEdge[]>("/intelligence/graph/edges", { query: params });
}

export async function getGraphNeighbors(entityType: string, entityId: string): Promise<GraphEdge[]> {
  return api<GraphEdge[]>("/intelligence/graph/neighbors", { query: { entity_type: entityType, entity_id: entityId } });
}

export async function getCollaborationPath(fromEmployee: string, toEmployee: string): Promise<GraphPathStep[]> {
  return api<GraphPathStep[]>("/intelligence/graph/path", { query: { from_employee: fromEmployee, to_employee: toEmployee } });
}

export async function getGraphBottlenecks(limit = 10): Promise<GraphPathStep[]> {
  return api<GraphPathStep[]>("/intelligence/graph/bottlenecks", { query: { limit } });
}

export async function deactivateGraphEdge(edgeId: string): Promise<{ ok: boolean }> {
  return api<{ ok: boolean }>(`/intelligence/graph/edges/${edgeId}`, { method: "DELETE" });
}

export async function listKnowledgeInsights(params: { kind?: string; status?: string; limit?: number } = {}): Promise<KnowledgeInsight[]> {
  return api<KnowledgeInsight[]>("/intelligence/knowledge/insights", { query: params });
}

export async function setKnowledgeInsightStatus(insightId: string, status: string): Promise<KnowledgeInsight> {
  return api<KnowledgeInsight>(`/intelligence/knowledge/insights/${insightId}`, { method: "PATCH", body: { status } });
}

export async function listSearchInsights(kind?: string, limit = 50): Promise<SearchInsight[]> {
  return api<SearchInsight[]>("/intelligence/search/insights", { query: { kind, limit } });
}

export async function getSearchStats(): Promise<SearchStats> {
  return api<SearchStats>("/intelligence/search/stats");
}

export async function listBurnoutSignals(minLevel = "moderate", status?: string, limit = 50): Promise<BurnoutSignal[]> {
  return api<BurnoutSignal[]>("/intelligence/burnout/signals", { query: { min_level: minLevel, status, limit } });
}

export async function setBurnoutSignalStatus(signalId: string, status: string): Promise<BurnoutSignal> {
  return api<BurnoutSignal>(`/intelligence/burnout/signals/${signalId}`, { method: "PATCH", body: { status } });
}

export async function listDuplicates(kind?: string, status = "open", limit = 50): Promise<DuplicateDetection[]> {
  return api<DuplicateDetection[]>("/intelligence/duplicates", { query: { kind, status, limit } });
}

export async function setDuplicateStatus(detectionId: string, status: string): Promise<DuplicateDetection> {
  return api<DuplicateDetection>(`/intelligence/duplicates/${detectionId}`, { method: "PATCH", body: { status } });
}

export async function listPatterns(patternType?: string, status = "open", limit = 50): Promise<PatternDetection[]> {
  return api<PatternDetection[]>("/intelligence/patterns", { query: { pattern_type: patternType, status, limit } });
}

export async function setPatternStatus(patternId: string, status: string): Promise<PatternDetection> {
  return api<PatternDetection>(`/intelligence/patterns/${patternId}`, { method: "PATCH", body: { status } });
}

export async function listWorkflowInsights(status = "open", limit = 50): Promise<WorkflowInsight[]> {
  return api<WorkflowInsight[]>("/intelligence/workflow/insights", { query: { status, limit } });
}

export async function setWorkflowInsightStatus(insightId: string, status: string): Promise<WorkflowInsight> {
  return api<WorkflowInsight>(`/intelligence/workflow/insights/${insightId}`, { method: "PATCH", body: { status } });
}

export async function listLearningLessons(eventType?: string, limit = 50): Promise<LearningLesson[]> {
  return api<LearningLesson[]>("/intelligence/learning/lessons", { query: { event_type: eventType, limit } });
}

export async function getLearningSummary(): Promise<LearningSummary> {
  return api<LearningSummary>("/intelligence/learning/summary");
}

export async function getCollaborationMetrics(): Promise<CollaborationMetrics> {
  return api<CollaborationMetrics>("/intelligence/collaboration");
}

export async function recomputeCollaboration(): Promise<CollaborationMetrics> {
  return api<CollaborationMetrics>("/intelligence/collaboration/recompute", { method: "POST" });
}

export async function listDailyBriefs(limit = 20): Promise<DailyBrief[]> {
  return api<DailyBrief[]>("/intelligence/briefs", { query: { limit } });
}

export async function getExecutiveBrief(): Promise<DailyBrief> {
  return api<DailyBrief>("/intelligence/briefs/executive");
}

export async function getEmployeeBrief(): Promise<DailyBrief> {
  return api<DailyBrief>("/intelligence/briefs/employee");
}

export async function generateBriefs(): Promise<{ executive: DailyBrief }> {
  return api<{ executive: DailyBrief }>("/intelligence/briefs/generate", { method: "POST" });
}

export async function getMyRecommendations(limit = 25): Promise<RecommendationItem[]> {
  return api<RecommendationItem[]>("/intelligence/recommendations", { query: { limit } });
}

export async function refreshMyRecommendations(): Promise<{ generated: number }> {
  return api<{ generated: number }>("/intelligence/recommendations/refresh", { method: "POST" });
}

export async function setRecommendationStatus(itemId: string, status: string): Promise<RecommendationItem> {
  return api<RecommendationItem>(`/intelligence/recommendations/${itemId}`, { method: "PATCH", body: { status } });
}

export async function getEventCatalog(): Promise<{ name: string; description: string; points?: number | null }[]> {
  return api<{ name: string; description: string; points?: number | null }[]>("/intelligence/catalog");
}

// ---------------------------------------------------------------- /insights (Phase 9.1 spec path)

export async function getInsightsFeed(limit = 10): Promise<InsightsFeed> {
  return api<InsightsFeed>("/insights", { query: { limit } });
}

export async function getInsightRisks(params: { level?: string; status?: string; limit?: number } = {}): Promise<{ total: number; risks: InsightRisk[] }> {
  return api<{ total: number; risks: InsightRisk[] }>("/insights/risks", { query: params });
}

export async function scanInsightRisks(): Promise<{ scanned: boolean; new_risks: number }> {
  return api<{ scanned: boolean; new_risks: number }>("/insights/risks/scan", { method: "POST" });
}

export async function getAutonomousNotifications(type?: string, limit = 50): Promise<AutonomousNotification[]> {
  return api<AutonomousNotification[]>("/insights/notifications", { query: { type, limit } });
}

export async function generateAutonomousNotifications(): Promise<{ generated: number }> {
  return api<{ generated: number }>("/insights/notifications/generate", { method: "POST" });
}

// ---------------------------------------------------------------- /recommendations (Phase 9.1 spec path)

export async function getMyRecommendationsFeed(limit = 25): Promise<RecommendationItem[]> {
  return api<RecommendationItem[]>("/recommendations", { query: { limit } });
}

export async function refreshMyRecommendationsFeed(): Promise<{ generated: number }> {
  return api<{ generated: number }>("/recommendations/refresh", { method: "POST" });
}

export async function setRecommendationFeedStatus(itemId: string, status: string): Promise<RecommendationItem> {
  return api<RecommendationItem>(`/recommendations/${itemId}`, { method: "PATCH", body: { status } });
}

// ---------------------------------------------------------------------------
// Phase 10 â€” Learning & Growth Operating System
// ---------------------------------------------------------------------------

export interface LearningProfile {
  id: string;
  employee_id: string;
  learning_score: number;
  level?: string;
  career_stage?: string;
  preferred_learning?: string;
  weekly_learning_hours?: number;
  completed_courses: number;
  certifications: number;
  mentor_id?: string | null;
  last_learning_date?: string | null;
  career_goals: string[];
  learning_goals: string[];
}

export interface LearningHistoryEntry {
  id: string;
  kind: string;
  title: string;
  entity_id?: string | null;
  score?: number;
  time_minutes?: number;
  certificate_id?: string | null;
  feedback?: string | null;
  meta?: Record<string, unknown> | null;
  occurred_at: string;
}

export interface Course {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  difficulty?: string;
  duration_minutes?: number;
  format?: string;
  department?: string | null;
  language?: string;
  status: string;
  external_url?: string | null;
  cover_url?: string | null;
  certificate_title?: string | null;
  skills: string[];
  tags: string[];
  enrollments?: number;
  my_progress?: number | null;
  my_enrollment_id?: string | null;
  modules?: { id: string; title: string; description?: string | null; position: number }[];
  lessons?: {
    id: string;
    title: string;
    module_id?: string | null;
    content_type?: string;
    external_url?: string | null;
    position: number;
    duration_minutes?: number;
  }[];
  quizzes?: { id: string; title: string; module_id?: string | null; question_count: number; passing_score: number }[];
}

export interface CourseEnrollment {
  id: string;
  course_id: string;
  title: string;
  category?: string | null;
  status: string;
  progress: number;
  enrolled_at: string;
  completed_at?: string | null;
}

export interface LearningPath {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  target_role?: string | null;
  difficulty?: string;
  estimated_days?: number | null;
  status: string;
  tags: string[];
  step_count?: number;
  enrolled?: boolean;
  my_progress?: number;
  steps?: {
    id: string;
    title: string;
    description?: string | null;
    course_id?: string | null;
    position: number;
    done?: boolean;
  }[];
}

export interface LearningPathEnrollment {
  id: string;
  path_id: string;
  title: string;
  target_role?: string | null;
  status: string;
  progress: number;
  completed_step_ids: string[];
  started_at: string;
  completed_at?: string | null;
}

export interface SkillGraphEntry {
  skill_id: string;
  name: string;
  category?: string | null;
  level: number;
  label: string;
  years_experience?: number;
  verified: boolean;
  source: string;
}

export interface LearningSkillGap {
  id?: string;
  skill_id?: string | null;
  skill_name: string;
  current_level: number;
  required_level: number;
  gap: number;
  priority: string;
  source?: string;
  status?: string;
}

export interface OrgSkillMap {
  date?: string;
  snapshot_id?: string | null;
  skills?: { name: string; category?: string | null; total_employees: number; average_level: number }[];
}

export interface Assessment {
  id: string;
  title: string;
  description?: string | null;
  kind: string;
  category: string;
  difficulty?: string;
  skills: string[];
  duration_minutes?: number;
  passing_score: number;
  question_count: number;
  status: string;
  linked_certification_id?: string | null;
  questions?: { id?: string; question: string; options?: string[]; type?: string; points?: number }[];
}

export interface AssessmentAttempt {
  id: string;
  assessment_id: string;
  assessment_title?: string;
  kind?: string | null;
  status: string;
  score?: number | null;
  passed?: boolean | null;
  submitted_at?: string | null;
  evaluated_at?: string | null;
  feedback?: string | null;
  evaluation?: string | null;
}

export interface Certification {
  id: string;
  name: string;
  issuer?: string;
  category?: string | null;
  description?: string | null;
  skills: string[];
  cost?: number | null;
  validity_years?: number;
  url?: string | null;
  status: string;
}

export interface EarnedCertification {
  id: string;
  certification_id?: string | null;
  name: string;
  category?: string | null;
  level?: string | null;
  issuer?: string;
  earned_at?: string | null;
  expiry_date?: string | null;
  credential_id?: string;
  status: string;
  course_id?: string | null;
}

export interface MentorProfile {
  exists: boolean;
  id?: string;
  employee_id?: string;
  bio?: string | null;
  topics?: string[];
  availability?: string;
  max_mentees?: number;
  is_active?: boolean;
}

export interface MentorMatch {
  id: string;
  employee_id: string;
  name: string;
  designation?: string | null;
  bio?: string | null;
  topics: string[];
  availability: string;
  max_mentees: number;
  active_mentees: number;
}

export interface MentorshipRequest {
  id: string;
  mentor_id: string;
  mentee_id: string;
  other_name?: string | null;
  other_designation?: string | null;
  topic: string;
  goals?: string[];
  status: string;
  requested_by?: string;
  started_at?: string | null;
  progress: number;
  session_count: number;
}

export interface CareerPath {
  id: string;
  title: string;
  description?: string | null;
  department?: string | null;
  levels: string[];
  status: string;
  step_count?: number;
  steps?: {
    id: string;
    title: string;
    position: number;
    level?: string;
    required_skills: { name?: string; skill?: string; level: number }[];
    required_years?: number;
    criteria?: Record<string, unknown>;
  }[];
}

export interface CareerProgress {
  employee_id?: string;
  path_id?: string;
  path_title?: string;
  current?: { id: string; title: string; position: number; level?: string; required_skills: { name?: string; skill?: string; level: number }[]; required_years?: number } | null;
  next?: { id: string; title: string; position: number; level?: string; required_skills: { name?: string; skill?: string; level: number }[]; required_years?: number } | null;
  current_role?: string | null;
  next_role?: string | null;
  readiness: number;
  evidence: { category: string; label: string; value: string; met: boolean }[];
  promotion_ready: boolean;
}

export interface PromotionSignal {
  id?: string;
  detected?: boolean;
  target_role?: string;
  readiness?: number;
  evidence?: { category: string; label: string; value: string; met: boolean }[];
  status?: string;
  employee_id?: string;
  employee_name?: string;
  designation?: string | null;
  score?: number;
}

export interface Academy {
  id: string;
  name: string;
  description?: string | null;
  category?: string | null;
  cover_url?: string | null;
  curriculum?: string[];
  status?: string;
  member_count?: number;
  course_count?: number;
  joined?: boolean;
}

export interface OnboardingPlan {
  id: string;
  employee_id: string;
  status: string;
  plan_status?: string;
  progress: number;
  start_date?: string | null;
  target_date?: string | null;
  mentor_id?: string | null;
  completed_at?: string | null;
  tasks?: {
    id: string;
    title: string;
    description?: string | null;
    category: string;
    kind: string;
    reference_id?: string | null;
    position: number;
    completed: boolean;
    completed_at?: string | null;
  }[];
}

export interface LearningRecommendationItem {
  id: string;
  kind: string;
  title: string;
  description?: string | null;
  reason?: string | null;
  score: number;
  source?: string;
  entity_id?: string | null;
  status: string;
  created_at?: string | null;
}

export interface LearningDashboard {
  profile: {
    learning_score: number;
    level?: string;
    career_stage?: string;
    completed_courses: number;
    certifications: number;
    weekly_learning_hours?: number;
    learning_goals: string[];
  };
  my_courses: { id: string; title: string; category?: string | null; difficulty?: string; duration_minutes?: number; progress: number; status: string; enrollment_id: string }[];
  recommended_courses: { id: string; title: string; category?: string | null; difficulty?: string }[];
  recommendations: LearningRecommendationItem[];
  certificates: EarnedCertification[];
  mentor?: { employee_id: string; name: string; designation?: string | null } | null;
  career: CareerProgress;
  learning_paths: { path_id: string; title?: string | null; progress: number; status: string }[];
  upcoming_assessments: { id: string; title: string; kind?: string | null; status: string }[];
  skill_gaps: { skill: string; priority: string; gap: number }[];
  trending: { id: string; title: string }[];
}

export interface AiLearningAnswer {
  intent: string;
  response?: string;
  answer?: string;
  suggestions?: string[];
  gaps?: { skill: string; current: number; required: number; priority: string }[];
  courses?: { id: string; title: string; category?: string | null }[];
  mentors?: { employee_id: string; name: string; topics: string[]; availability: string }[];
  readiness?: number;
  next?: unknown;
  evidence?: { category: string; label: string; value: string; met: boolean }[];
  certifications?: { id: string; name: string; level?: string }[];
  roadmap?: unknown;
  plan?: unknown;
}

// ---------------------------------------------------------------- learning foundation

export async function getLearningProfile(): Promise<LearningProfile> {
  return api<LearningProfile>("/learning/profile");
}

export async function updateLearningProfile(payload: Record<string, unknown>): Promise<LearningProfile> {
  return api<LearningProfile>("/learning/profile", { method: "PATCH", body: payload });
}

export async function getLearningHistory(limit = 50): Promise<LearningHistoryEntry[]> {
  return api<LearningHistoryEntry[]>("/learning/history", { query: { limit } });
}

export async function getLearningDashboard(): Promise<LearningDashboard> {
  return api<LearningDashboard>("/learning/dashboard");
}

export async function askLearningAi(question: string): Promise<AiLearningAnswer> {
  return api<AiLearningAnswer>("/learning/ai/ask", { method: "POST", body: { question } });
}

// ---------------------------------------------------------------- courses

export async function listCourses(query: {
  category?: string;
  difficulty?: string;
  search?: string;
  status?: string;
  limit?: number;
} = {}): Promise<Course[]> {
  return api<Course[]>("/learning/courses", { query });
}

export async function getCourse(id: string): Promise<Course> {
  return api<Course>(`/learning/courses/${id}`);
}

export async function createCourse(payload: Record<string, unknown>): Promise<Course> {
  return api<Course>("/learning/courses", { method: "POST", body: payload });
}

export async function updateCourse(id: string, payload: Record<string, unknown>): Promise<Course> {
  return api<Course>(`/learning/courses/${id}`, { method: "PATCH", body: payload });
}

export async function deleteCourse(id: string): Promise<{ deleted: boolean }> {
  return api<{ deleted: boolean }>(`/learning/courses/${id}`, { method: "DELETE" });
}

export async function getCourseCategories(): Promise<string[]> {
  return api<string[]>("/learning/courses/categories");
}

export async function listTrendingCourses(limit = 6): Promise<{ id: string; title: string; category?: string | null; difficulty?: string; duration_minutes?: number; enrollments?: number }[]> {
  return api("/learning/courses/trending", { query: { limit } });
}

export async function addCourseModule(courseId: string, payload: Record<string, unknown>) {
  return api(`/learning/courses/${courseId}/modules`, { method: "POST", body: payload });
}

export async function addCourseLesson(courseId: string, payload: Record<string, unknown>) {
  return api(`/learning/courses/${courseId}/lessons`, { method: "POST", body: payload });
}

export async function addCourseQuiz(courseId: string, payload: Record<string, unknown>) {
  return api(`/learning/courses/${courseId}/quizzes`, { method: "POST", body: payload });
}

export async function enrollCourse(courseId: string): Promise<{ id: string; course_id: string; status: string; progress: number }> {
  return api(`/learning/courses/${courseId}/enroll`, { method: "POST" });
}

export async function myCourseEnrollments(): Promise<CourseEnrollment[]> {
  return api<CourseEnrollment[]>("/learning/courses/my/enrollments");
}

export async function completeCourseLesson(enrollmentId: string, lessonId: string): Promise<{ id: string; status: string; progress: number }> {
  return api(`/learning/courses/enrollments/${enrollmentId}/lessons/${lessonId}/complete`, { method: "POST" });
}

export async function completeCourse(enrollmentId: string): Promise<{ id: string; status: string; progress: number }> {
  return api(`/learning/courses/enrollments/${enrollmentId}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- learning paths

export async function listLearningPaths(query: { status?: string; search?: string; limit?: number } = {}): Promise<LearningPath[]> {
  return api<LearningPath[]>("/learning/paths", { query });
}

export async function getLearningPath(id: string): Promise<LearningPath> {
  return api<LearningPath>(`/learning/paths/${id}`);
}

export async function createLearningPath(payload: Record<string, unknown>): Promise<LearningPath> {
  return api<LearningPath>("/learning/paths", { method: "POST", body: payload });
}

export async function myLearningPathEnrollments(): Promise<LearningPathEnrollment[]> {
  return api<LearningPathEnrollment[]>("/learning/paths/my/enrollments");
}

export async function enrollLearningPath(pathId: string): Promise<{ id: string; path_id: string; status: string }> {
  return api(`/learning/paths/${pathId}/enroll`, { method: "POST" });
}

export async function completePathStep(enrollmentId: string, stepId: string): Promise<{ id: string; status: string; progress: number }> {
  return api(`/learning/paths/enrollments/${enrollmentId}/steps/${stepId}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- skills

export async function getMySkillGraph(): Promise<SkillGraphEntry[]> {
  return api<SkillGraphEntry[]>("/learning/skills");
}

export async function getOrgSkillMap(): Promise<OrgSkillMap> {
  return api<OrgSkillMap>("/learning/skills/org-map");
}

export async function refreshSkillSnapshot(): Promise<{ snapshot_id: string | null; date: string | null; skill_count: number }> {
  return api("/learning/skills/snapshot/refresh", { method: "POST" });
}

export async function getMySkillGaps(status = "open"): Promise<LearningSkillGap[]> {
  return api<LearningSkillGap[]>("/learning/skills/gaps", { query: { status } });
}

export async function refreshSkillGaps(): Promise<{ employee_id: string; gaps: number }> {
  return api("/learning/skills/gaps/refresh", { method: "POST" });
}

export async function closeSkillGap(gapId: string, status = "closed"): Promise<{ id: string; skill_name: string; status: string }> {
  return api(`/learning/skills/gaps/${gapId}/close`, { method: "POST", query: { status } });
}

export async function whoHasSkill(skillName: string, minLevel = 3, limit = 20): Promise<{ employee_id: string; name: string; designation?: string | null; level: number }[]> {
  return api(`/learning/skills/who/${encodeURIComponent(skillName)}`, { query: { min_level: minLevel, limit } });
}

export async function canMentorSkill(skillName: string, minLevel = 4): Promise<{ employee_id: string; name: string; designation?: string | null; level: number }[]> {
  return api(`/learning/skills/mentors/${encodeURIComponent(skillName)}`, { query: { min_level: minLevel } });
}

export async function boostSkill(skillName: string, payload: { employee_id?: string; points?: number; reason?: string } = {}): Promise<{ skill_name: string; level: number; verified: boolean }> {
  return api(`/learning/skills/${encodeURIComponent(skillName)}/boost`, { method: "POST", body: payload });
}

export async function setSkillLevel(skillName: string, payload: { employee_id?: string; level: number }): Promise<{ skill_name: string; level: number; verified: boolean }> {
  return api(`/learning/skills/${encodeURIComponent(skillName)}/set-level`, { method: "POST", body: payload });
}

// ---------------------------------------------------------------- assessments

export async function listAssessments(query: { category?: string; status?: string; limit?: number } = {}): Promise<Assessment[]> {
  return api<Assessment[]>("/learning/assessments", { query });
}

export async function getAssessment(id: string): Promise<Assessment> {
  return api<Assessment>(`/learning/assessments/${id}`);
}

export async function createAssessment(payload: Record<string, unknown>): Promise<Assessment> {
  return api<Assessment>("/learning/assessments", { method: "POST", body: payload });
}

export async function myAssessmentAttempts(status?: string): Promise<AssessmentAttempt[]> {
  return api<AssessmentAttempt[]>("/learning/assessments/my/attempts", { query: { status } });
}

export async function assignAssessment(assessmentId: string, employeeId?: string): Promise<{ id: string; assessment_id: string; status: string }> {
  return api(`/learning/assessments/${assessmentId}/assign`, { method: "POST", body: { employee_id: employeeId } });
}

export async function submitAssessmentAttempt(attemptId: string, answers: Record<string, unknown>): Promise<{ id: string; status: string; score: number | null; passed: boolean | null; submitted_at: string | null }> {
  return api(`/learning/assessments/attempts/${attemptId}/submit`, { method: "POST", body: { answers } });
}

export async function evaluateAssessmentAttempt(attemptId: string, payload: { reviewer_id?: string; score?: number; feedback?: string } = {}): Promise<{ id: string; status: string; score: number | null; passed: boolean | null; finalized_at: string | null }> {
  return api(`/learning/assessments/attempts/${attemptId}/evaluate`, { method: "POST", body: payload });
}

// ---------------------------------------------------------------- certifications

export async function listCertifications(query: { category?: string; status?: string; limit?: number } = {}): Promise<Certification[]> {
  return api<Certification[]>("/learning/certifications", { query });
}

export async function getCertification(id: string): Promise<Certification> {
  return api<Certification>(`/learning/certifications/${id}`);
}

export async function createCertification(payload: Record<string, unknown>): Promise<Certification> {
  return api<Certification>("/learning/certifications", { method: "POST", body: payload });
}

export async function myEarnedCertifications(status?: string): Promise<EarnedCertification[]> {
  return api<EarnedCertification[]>("/learning/certifications/my/earned", { query: { status } });
}

export async function recommendedCertifications(limit = 5): Promise<Certification[]> {
  return api<Certification[]>("/learning/certifications/my/recommended", { query: { limit } });
}

export async function startCertificationAttempt(certificationId: string): Promise<{ id: string; certification_id: string; status: string; started_at: string | null }> {
  return api(`/learning/certifications/${certificationId}/attempts`, { method: "POST" });
}

export async function completeCertificationAttempt(attemptId: string, payload: { score: number; passed: boolean; evidence?: string }): Promise<{ id: string; status: string; score: number | null; passed: boolean; credential_id?: string | null }> {
  return api(`/learning/certifications/attempts/${attemptId}/complete`, { method: "POST", body: payload });
}

// ---------------------------------------------------------------- mentorship

export async function getMentorProfile(): Promise<MentorProfile> {
  return api<MentorProfile>("/learning/mentorship/profile");
}

export async function upsertMentorProfile(payload: Record<string, unknown>): Promise<{ id: string; employee_id: string; is_active: boolean }> {
  return api(`/learning/mentorship/profile`, { method: "POST", body: payload });
}

export async function listMentors(query: { category?: string; search?: string; limit?: number } = {}): Promise<MentorMatch[]> {
  return api<MentorMatch[]>("/learning/mentorship/mentors", { query });
}

export async function recommendMentors(skill?: string, limit = 5): Promise<MentorMatch[]> {
  return api<MentorMatch[]>("/learning/mentorship/mentors/recommend", { query: { skill, limit } });
}

export async function requestMentorship(mentorId: string, payload: { topic: string; goals?: string[] }): Promise<{ id: string; status: string; topic: string }> {
  return api(`/learning/mentorship/mentors/${mentorId}/request`, { method: "POST", body: payload });
}

export async function listMentorshipRequests(role = "mentee", status?: string): Promise<MentorshipRequest[]> {
  return api<MentorshipRequest[]>("/learning/mentorship/requests", { query: { role, status } });
}

export async function respondToMentorship(mentorshipId: string, accept: boolean): Promise<{ id: string; status: string }> {
  return api(`/learning/mentorship/${mentorshipId}/respond`, { method: "POST", body: { accept } });
}

export async function addMentorshipSession(mentorshipId: string, payload: { title?: string; notes?: string; kind?: string; duration_minutes?: number }): Promise<{ id: string; title: string; kind: string }> {
  return api(`/learning/mentorship/${mentorshipId}/sessions`, { method: "POST", body: payload });
}

export async function addMentorshipFeedback(mentorshipId: string, payload: { rating: number; comment?: string }): Promise<{ id: string; rating: number }> {
  return api(`/learning/mentorship/${mentorshipId}/feedback`, { method: "POST", body: payload });
}

export async function completeMentorship(mentorshipId: string): Promise<{ id: string; status: string; progress: number }> {
  return api(`/learning/mentorship/${mentorshipId}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- career

export async function listCareerPaths(department?: string): Promise<CareerPath[]> {
  return api<CareerPath[]>("/learning/career", { query: { department } });
}

export async function getCareerPath(id: string): Promise<CareerPath> {
  return api<CareerPath>(`/learning/career/${id}`);
}

export async function createCareerPath(payload: Record<string, unknown>): Promise<CareerPath> {
  return api<CareerPath>("/learning/career", { method: "POST", body: payload });
}

export async function getMyCareerProgress(): Promise<CareerProgress> {
  return api<CareerProgress>("/learning/career/my/progress");
}

export async function getMyRequiredSkills(): Promise<{ skill: string; level: number }[]> {
  return api<{ skill: string; level: number }[]>("/learning/career/my/required-skills");
}

export async function detectPromotionSignal(): Promise<PromotionSignal> {
  return api<PromotionSignal>("/learning/career/my/promotion-signals/detect", { method: "POST" });
}

export async function listPromotionSignals(status = "open"): Promise<PromotionSignal[]> {
  return api<PromotionSignal[]>("/learning/career/signals", { query: { status } });
}

export async function reviewPromotionSignal(signalId: string, status: string): Promise<{ id: string; status: string }> {
  return api(`/learning/career/signals/${signalId}/review`, { method: "POST", body: { status } });
}

// ---------------------------------------------------------------- academies

export async function listAcademies(query: { category?: string; status?: string; limit?: number } = {}): Promise<Academy[]> {
  return api<Academy[]>("/learning/academies", { query });
}

export async function getAcademy(id: string): Promise<Academy> {
  return api<Academy>(`/learning/academies/${id}`);
}

export async function createAcademy(payload: Record<string, unknown>): Promise<Academy> {
  return api<Academy>("/learning/academies", { method: "POST", body: payload });
}

export async function myAcademies(): Promise<Academy[]> {
  return api<Academy[]>("/learning/academies/my");
}

export async function addAcademyCourse(academyId: string, courseId: string): Promise<{ id: string; academy_id: string; course_id: string }> {
  return api(`/learning/academies/${academyId}/courses`, { method: "POST", body: { course_id: courseId } });
}

export async function removeAcademyCourse(academyId: string, courseId: string): Promise<{ removed: boolean }> {
  return api(`/learning/academies/${academyId}/courses/${courseId}`, { method: "DELETE" });
}

export async function joinAcademy(academyId: string): Promise<{ id: string; academy_id: string; joined: boolean }> {
  return api(`/learning/academies/${academyId}/join`, { method: "POST" });
}

export async function leaveAcademy(academyId: string): Promise<{ left: boolean }> {
  return api<{ left: boolean }>(`/learning/academies/${academyId}/leave`, { method: "POST" });
}

// ---------------------------------------------------------------- onboarding

export async function createOnboardingPlan(employeeId: string, targetDays = 14): Promise<{ id: string; employee_id: string; status: string }> {
  return api(`/learning/onboarding/plans`, { method: "POST", body: { employee_id: employeeId, target_days: targetDays } });
}

export async function listOnboardingPlans(status = "active"): Promise<{ id: string; employee_id: string; status: string; progress: number }[]> {
  return api(`/learning/onboarding/plans`, { query: { status } });
}

export async function getOnboardingPlan(id: string): Promise<OnboardingPlan> {
  return api<OnboardingPlan>(`/learning/onboarding/plans/${id}`);
}

export async function completeOnboardingTask(planId: string, taskId: string): Promise<{ plan_id: string; task_id: string; plan_progress: number; plan_status: string }> {
  return api(`/learning/onboarding/plans/${planId}/tasks/${taskId}/complete`, { method: "POST" });
}

// ---------------------------------------------------------------- learning recommendations (Phase 10 feed)

export async function getLearningRecommendations(limit = 25): Promise<LearningRecommendationItem[]> {
  return api<LearningRecommendationItem[]>("/recommendations", { query: { limit } });
}

export async function refreshLearningRecommendations(): Promise<{ generated: number }> {
  return api<{ generated: number }>("/recommendations/refresh", { method: "POST" });
}

export async function setLearningRecommendationStatus(itemId: string, status: string): Promise<LearningRecommendationItem> {
  return api<LearningRecommendationItem>(`/recommendations/${itemId}`, { method: "PATCH", body: { status } });
}

// ---------------------------------------------------------------- HR hub

export interface HrDashboard {
  workforce: {
    headcount: number;
    hires_month: number;
    exits_month: number;
    attrition_rate: number;
    trend: { date: string; headcount: number; hires: number; exits: number; attrition: number }[];
    succession_pipeline: { total: number; ready: number; developing: number };
    hiring_needs: {
      by_department: { department: string; open_positions: number; plan_growth: number; priority: string }[];
      total_open_positions: number;
      attrition_rate: number;
      attrition_pressure: boolean;
      last_snapshot_date: string | null;
    };
    headcount_status: { active: number; total: number };
  };
  recruitment: {
    open_jobs: number;
    open_positions: number;
    total_jobs: number;
    total_candidates: number;
    candidates_by_stage: Record<string, number>;
    interviews_scheduled: number;
    offers: { total: number; sent: number; accepted: number; declined: number };
    hires: number;
  };
  leave: {
    status_counts: Record<string, number>;
    pending_count: number;
    approved_count: number;
    per_type: { code: string; name: string; requests: number; days: number }[];
    active_employees: number;
  };
  performance: {
    cycles: { total: number; open: number; reviewing: number };
    reviews: { total: number; draft: number; submitted: number; completed: number; average_rating: number };
    goals: { total: number; active: number; completed: number };
  };
  offboarding: { active: number; completed: number; in_progress: number; list: OffboardingItem[] };
  compliance: {
    expired_documents: number;
    expiring_30: number;
    missing_trainings: number;
    total_documents: number;
  };
  assets: {
    total: number;
    assigned: number;
    available: number;
    in_maintenance: number;
    lost: number;
    returned: number;
    by_status: Record<string, number>;
    by_category: Record<string, number>;
  };
  wellbeing: {
    total_checks: number;
    low: number;
    medium: number;
    high: number;
    at_risk_employees: number;
    latest_high: {
      id: string;
      employee_id: string;
      employee_name?: string | null;
      check_date: string;
      metrics: Record<string, unknown>;
      risk_level: string;
      signals: string[];
      notes?: string | null;
      reviewed: boolean;
    }[];
  };
  payroll: {
    runs: { total: number; synced: number; pending: number; failed: number };
    active_providers: number;
    last_run: PayrollRun | null;
  };
}

export interface HrAiAnswer {
  answer: string;
  context?: string[];
  question?: string;
  summary?: string;
}

export async function getHrDashboard(): Promise<HrDashboard> {
  return api<HrDashboard>("/hr/dashboard");
}

export async function askHrAi(question: string): Promise<HrAiAnswer> {
  return api<HrAiAnswer>("/hr/ai/ask", { method: "POST", body: { question } });
}

export async function promoteEmployee(employeeId: string, payload: Record<string, unknown>): Promise<{ employee_id: string; previous_designation: string | null; new_designation: string | null }> {
  return api(`/hr/employees/${employeeId}/promote`, { method: "POST", body: payload });
}

export async function transferEmployee(employeeId: string, payload: Record<string, unknown>): Promise<{ employee_id: string; department_id: string | null; team_id: string | null; manager_id: string | null }> {
  return api(`/hr/employees/${employeeId}/transfer`, { method: "POST", body: payload });
}

export interface EmployeeLifecycle {
  employee: { id: string; name: string; designation: string | null; status: string; joining_date: string | null };
  attendance: {
    employee_id: string;
    start: string;
    end: string;
    days: number;
    statuses: Record<string, number>;
    total_minutes: number;
    average_minutes: number;
    overtime_minutes: number;
    late_minutes: number;
  };
  leave: { balances: LeaveBalance[] };
  performance: {
    employee_id: string;
    reviews: number;
    average_rating: number;
    goals_active: number;
    goals_completed: number;
    goal_progress: number;
  };
  assets: Asset[];
  compliance: { documents: ComplianceDocument[]; trainings: TrainingCompletion[] };
  offboarding: OffboardingItem | null;
}

export async function getEmployeeLifecycle(employeeId: string): Promise<EmployeeLifecycle> {
  return api<EmployeeLifecycle>(`/hr/employees/${employeeId}/lifecycle`);
}

// ---------------------------------------------------------------- attendance

export interface Shift {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
  work_hours: number;
  break_minutes: number;
  days: string[];
  timezone: string | null;
  is_flexible: boolean;
  is_active: boolean;
}

export interface Holiday {
  id: string;
  name: string;
  date: string;
  kind: string;
  optional: boolean;
}

export interface AttendanceRecord {
  id: string;
  employee_id?: string;
  date: string;
  work_mode: string;
  status: string;
  check_in: string | null;
  check_out: string | null;
  work_minutes: number;
  late_minutes: number;
  early_departure_minutes?: number;
  overtime_minutes: number;
  source: string;
  location?: string | null;
  note?: string | null;
}

export interface TodayStatus {
  checked_in: boolean;
  checked_out?: boolean;
  record_id?: string;
  date?: string;
  check_in?: string | null;
  check_out?: string | null;
  status?: string;
  work_mode?: string;
  work_minutes?: number;
}

export interface AttendanceSummary {
  employee_id: string;
  start: string;
  end: string;
  days: number;
  statuses: Record<string, number>;
  total_minutes: number;
  average_minutes: number;
  overtime_minutes: number;
  late_minutes: number;
}

export interface AttendanceCorrection {
  id: string;
  employee_id: string;
  attendance_id: string | null;
  requested_date: string;
  reason: string | null;
  status: string;
  adjusted_check_in: string | null;
  adjusted_check_out: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export async function listShifts(activeOnly = false): Promise<Shift[]> {
  return api<Shift[]>("/attendance/shifts", { query: { active_only: activeOnly } });
}

export async function createShift(payload: Record<string, unknown>): Promise<{ id: string; name: string }> {
  return api(`/attendance/shifts`, { method: "POST", body: payload });
}

export async function updateShift(shiftId: string, payload: Record<string, unknown>): Promise<{ id: string; name: string }> {
  return api(`/attendance/shifts/${shiftId}`, { method: "PATCH", body: payload });
}

export async function deleteShift(shiftId: string): Promise<{ deleted: boolean }> {
  return api(`/attendance/shifts/${shiftId}`, { method: "DELETE" });
}

export async function listHolidays(year?: number): Promise<Holiday[]> {
  return api<Holiday[]>("/attendance/holidays", { query: { year } });
}

export async function addHoliday(payload: Record<string, unknown>): Promise<{ id: string; name: string; date: string }> {
  return api(`/attendance/holidays`, { method: "POST", body: payload });
}

export async function deleteHoliday(holidayId: string): Promise<{ deleted: boolean }> {
  return api(`/attendance/holidays/${holidayId}`, { method: "DELETE" });
}

export async function clockIn(payload: Record<string, unknown> = {}): Promise<{ id: string; date: string; check_in: string | null; status: string; work_mode: string }> {
  return api(`/attendance/clock-in`, { method: "POST", body: payload });
}

export async function clockOut(payload: Record<string, unknown> = {}): Promise<{ id: string; date: string; check_in: string | null; check_out: string | null; work_minutes: number; late_minutes: number; overtime_minutes: number }> {
  return api(`/attendance/clock-out`, { method: "POST", body: payload });
}

export async function startBreak(minutes = 30): Promise<{ on_break: boolean; breaks: unknown[] }> {
  return api(`/attendance/breaks`, { method: "POST", body: { minutes } });
}

export async function endBreak(): Promise<{ on_break: boolean; breaks: unknown[] }> {
  return api(`/attendance/breaks/end`, { method: "POST" });
}

export async function getTodayStatus(): Promise<TodayStatus> {
  return api<TodayStatus>("/attendance/today");
}

export async function myAttendanceRecords(query: { start?: string; end?: string; limit?: number } = {}): Promise<AttendanceRecord[]> {
  return api<AttendanceRecord[]>("/attendance/my", { query });
}

export async function listAttendanceRecords(query: { employee_id?: string; start?: string; end?: string; limit?: number } = {}): Promise<AttendanceRecord[]> {
  return api<AttendanceRecord[]>("/attendance", { query });
}

export async function recordManualAttendance(payload: Record<string, unknown>): Promise<{ id: string; date: string; status: string }> {
  return api(`/attendance/manual`, { method: "POST", body: payload });
}

export async function getAttendanceSummary(query: { employee_id?: string; start?: string; end?: string } = {}): Promise<AttendanceSummary> {
  return api<AttendanceSummary>("/attendance/summary", { query });
}

export async function requestAttendanceCorrection(payload: Record<string, unknown>): Promise<{ id: string; requested_date: string; status: string }> {
  return api(`/attendance/corrections`, { method: "POST", body: payload });
}

export async function listAttendanceCorrections(query: { employee_id?: string; status?: string } = {}): Promise<AttendanceCorrection[]> {
  return api<AttendanceCorrection[]>("/attendance/corrections", { query });
}

export async function reviewAttendanceCorrection(correctionId: string, decision: string): Promise<{ id: string; status: string }> {
  return api(`/attendance/corrections/${correctionId}/review`, { method: "POST", body: { decision } });
}

// ---------------------------------------------------------------- leave

export interface LeaveType {
  id: string;
  name: string;
  code: string;
  color: string;
  days_per_year: number;
  carry_over: number;
  requires_approval: boolean;
  is_paid: boolean;
  is_active: boolean;
}

export interface LeaveBalance {
  leave_type_id: string;
  code: string;
  name: string;
  color: string;
  is_paid: boolean;
  allocated: number;
  carried_over: number;
  used: number;
  remaining: number;
}

export interface LeaveRequestItem {
  id: string;
  employee_id: string;
  employee_name?: string | null;
  leave_type_id: string;
  leave_type: string | null;
  leave_type_name: string | null;
  color: string;
  start_date: string;
  end_date: string;
  days: number;
  half_day: boolean;
  reason: string | null;
  status: string;
  approved_by?: string | null;
  approved_at?: string | null;
  backup_employee_id?: string | null;
  reviewer_note?: string | null;
}

export interface LeaveSummary {
  status_counts: Record<string, number>;
  pending_count: number;
  approved_count: number;
  per_type: { code: string; name: string; requests: number; days: number }[];
  active_employees: number;
}

export async function listLeaveTypes(): Promise<LeaveType[]> {
  return api<LeaveType[]>("/leave/types");
}

export async function createLeaveType(payload: Record<string, unknown>): Promise<{ id: string; name: string; code: string }> {
  return api(`/leave/types`, { method: "POST", body: payload });
}

export async function updateLeaveType(leaveTypeId: string, payload: Record<string, unknown>): Promise<{ id: string; name: string }> {
  return api(`/leave/types/${leaveTypeId}`, { method: "PATCH", body: payload });
}

export async function myLeaveBalances(year?: number): Promise<LeaveBalance[]> {
  return api<LeaveBalance[]>("/leave/balances", { query: { year } });
}

export async function employeeLeaveBalances(employeeId: string, year?: number): Promise<LeaveBalance[]> {
  return api<LeaveBalance[]>(`/leave/balances/${employeeId}`, { query: { year } });
}

export async function requestLeave(payload: Record<string, unknown>): Promise<{ id: string; start_date: string; end_date: string; days: number; status: string }> {
  return api(`/leave/requests`, { method: "POST", body: payload });
}

export async function listLeaveRequests(query: { employee_id?: string; status?: string; start?: string; end?: string; mine?: boolean } = {}): Promise<LeaveRequestItem[]> {
  return api<LeaveRequestItem[]>("/leave/requests", { query });
}

export async function getLeaveRequest(requestId: string): Promise<LeaveRequestItem> {
  return api<LeaveRequestItem>(`/leave/requests/${requestId}`);
}

export async function pendingLeaveRequests(): Promise<LeaveRequestItem[]> {
  return api<LeaveRequestItem[]>("/leave/pending");
}

export async function approveLeaveRequest(requestId: string, note?: string): Promise<{ id: string; status: string }> {
  return api(`/leave/requests/${requestId}/approve`, { method: "POST", body: { note } });
}

export async function rejectLeaveRequest(requestId: string, note?: string): Promise<{ id: string; status: string }> {
  return api(`/leave/requests/${requestId}/reject`, { method: "POST", body: { note } });
}

export async function cancelLeaveRequest(requestId: string): Promise<{ id: string; status: string }> {
  return api(`/leave/requests/${requestId}/cancel`, { method: "POST" });
}

export async function getLeaveSummary(): Promise<LeaveSummary> {
  return api<LeaveSummary>("/leave/summary");
}

// ---------------------------------------------------------------- recruitment

export interface Job {
  id: string;
  title: string;
  department: string | null;
  location: string | null;
  employment_type: string | null;
  description: string | null;
  requirements: string[];
  skills: string[];
  salary_range: string | null;
  openings: number;
  status: string;
  created_at: string | null;
}

export interface Candidate {
  id: string;
  job_id: string;
  job_title: string | null;
  name: string;
  email: string | null;
  phone: string | null;
  resume_url: string | null;
  source: string;
  stage: string;
  skills: string[];
  experience_years: number;
  current_company: string | null;
  current_title: string | null;
  match_score: number;
  rating: number | null;
  notes: string | null;
  applied_at: string | null;
}

export interface Interview {
  id: string;
  job_id: string;
  job_title: string | null;
  candidate_id: string;
  candidate_name: string | null;
  scheduled_at: string | null;
  duration_minutes: number;
  panel: string[];
  mode: string;
  status: string;
  rating: number | null;
  summary: string | null;
  feedback: string[];
}

export interface Offer {
  id: string;
  job_id: string;
  job_title: string | null;
  candidate_id: string;
  candidate_name: string | null;
  salary: number | null;
  equity: string | null;
  start_date: string | null;
  expires_at: string | null;
  status: string;
  notes: string | null;
  signed_at: string | null;
}

export interface RecruitmentStats {
  open_jobs: number;
  open_positions: number;
  total_jobs: number;
  total_candidates: number;
  candidates_by_stage: Record<string, number>;
  interviews_scheduled: number;
  offers: { total: number; sent: number; accepted: number; declined: number };
  hires: number;
}

export async function listRecruitmentJobs(status?: string): Promise<Job[]> {
  return api<Job[]>("/recruitment/jobs", { query: { status } });
}

export async function createRecruitmentJob(payload: Record<string, unknown>): Promise<{ id: string; title: string; status: string }> {
  return api(`/recruitment/jobs`, { method: "POST", body: payload });
}

export async function updateRecruitmentJob(jobId: string, payload: Record<string, unknown>): Promise<{ id: string; title: string; status: string }> {
  return api(`/recruitment/jobs/${jobId}`, { method: "PATCH", body: payload });
}

export async function closeRecruitmentJob(jobId: string): Promise<{ id: string; status: string }> {
  return api(`/recruitment/jobs/${jobId}/close`, { method: "POST" });
}

export async function listCandidates(query: { job_id?: string; stage?: string } = {}): Promise<Candidate[]> {
  return api<Candidate[]>("/recruitment/candidates", { query });
}

export async function addCandidate(payload: Record<string, unknown>): Promise<{ id: string; name: string; stage: string; match_score: number }> {
  return api(`/recruitment/candidates`, { method: "POST", body: payload });
}

export async function updateCandidate(candidateId: string, payload: Record<string, unknown>): Promise<{ id: string; stage: string; match_score: number }> {
  return api(`/recruitment/candidates/${candidateId}`, { method: "PATCH", body: payload });
}

export async function listInterviews(query: { job_id?: string; candidate_id?: string } = {}): Promise<Interview[]> {
  return api<Interview[]>("/recruitment/interviews", { query });
}

export async function scheduleInterview(payload: Record<string, unknown>): Promise<{ id: string; status: string; scheduled_at: string | null }> {
  return api(`/recruitment/interviews`, { method: "POST", body: payload });
}

export async function completeInterview(interviewId: string, payload: Record<string, unknown>): Promise<{ id: string; status: string; rating: number | null }> {
  return api(`/recruitment/interviews/${interviewId}/complete`, { method: "POST", body: payload });
}

export async function listOffers(query: { candidate_id?: string; status?: string } = {}): Promise<Offer[]> {
  return api<Offer[]>("/recruitment/offers", { query });
}

export async function createOffer(payload: Record<string, unknown>): Promise<{ id: string; status: string; candidate_id: string }> {
  return api(`/recruitment/offers`, { method: "POST", body: payload });
}

export async function updateOfferStatus(offerId: string, status: string, notes?: string): Promise<{ id: string; status: string; hired_employee_id: string | null; hired_employee_name: string | null }> {
  return api(`/recruitment/offers/${offerId}/status`, { method: "POST", body: { status, notes } });
}

export async function getRecruitmentStats(): Promise<RecruitmentStats> {
  return api<RecruitmentStats>("/recruitment/stats");
}

// ---------------------------------------------------------------- performance

export interface PerformanceCycle {
  id: string;
  name: string;
  period: Record<string, unknown>;
  status: string;
  description: string | null;
  created_at: string | null;
}

export interface PerformanceGoal {
  id: string;
  employee_id: string;
  cycle_id: string | null;
  title: string;
  kind: string;
  status: string;
  progress: number;
  weight: number;
  due_date: string | null;
  description: string | null;
}

export interface PerformanceReview {
  id: string;
  cycle_id: string | null;
  employee_id: string;
  employee_name: string | null;
  reviewer_id: string | null;
  reviewer_name: string | null;
  kind: string;
  status: string;
  rating: number | null;
  feedback: string | null;
  strengths: string[];
  improvements: string[];
  learning_plan: string[];
  ai_summary: string | null;
  submitted_at: string | null;
  completed_at: string | null;
}

export interface PerformanceSummary {
  cycles: { total: number; open: number; reviewing: number };
  reviews: { total: number; draft: number; submitted: number; completed: number; average_rating: number };
  goals: { total: number; active: number; completed: number };
}

export async function listPerformanceCycles(status?: string): Promise<PerformanceCycle[]> {
  return api<PerformanceCycle[]>("/performance/cycles", { query: { status } });
}

export async function createPerformanceCycle(payload: Record<string, unknown>): Promise<{ id: string; name: string; status: string }> {
  return api(`/performance/cycles`, { method: "POST", body: payload });
}

export async function setCycleStatus(cycleId: string, status: string): Promise<{ id: string; status: string }> {
  return api(`/performance/cycles/${cycleId}/status`, { method: "POST", body: { status } });
}

export async function listPerformanceGoals(query: { employee_id?: string; cycle_id?: string; status?: string } = {}): Promise<PerformanceGoal[]> {
  return api<PerformanceGoal[]>("/performance/goals", { query });
}

export async function createPerformanceGoal(payload: Record<string, unknown>): Promise<{ id: string; title: string; status: string }> {
  return api(`/performance/goals`, { method: "POST", body: payload });
}

export async function updateGoalProgress(goalId: string, progress: number): Promise<{ id: string; progress: number; status: string }> {
  return api(`/performance/goals/${goalId}/progress`, { method: "PATCH", body: { progress } });
}

export async function listPerformanceReviews(query: { employee_id?: string; reviewer_id?: string; cycle_id?: string; status?: string } = {}): Promise<PerformanceReview[]> {
  return api<PerformanceReview[]>("/performance/reviews", { query });
}

export async function createPerformanceReview(payload: Record<string, unknown>): Promise<{ id: string; kind: string; status: string }> {
  return api(`/performance/reviews`, { method: "POST", body: payload });
}

export async function submitPerformanceReview(reviewId: string, payload: Record<string, unknown>): Promise<{ id: string; status: string; rating: number | null }> {
  return api(`/performance/reviews/${reviewId}/submit`, { method: "POST", body: payload });
}

export async function completePerformanceReview(reviewId: string): Promise<{ id: string; status: string; ai_summary: string | null }> {
  return api(`/performance/reviews/${reviewId}/complete`, { method: "POST" });
}

export async function getPerformanceSummary(): Promise<PerformanceSummary> {
  return api<PerformanceSummary>("/performance/summary");
}

// ---------------------------------------------------------------- assets

export interface Asset {
  id: string;
  employee_id: string | null;
  employee_name: string | null;
  name: string;
  category: string;
  serial_number: string | null;
  purchase_date: string | null;
  warranty_until: string | null;
  status: string;
  condition: string | null;
  notes: string | null;
  assigned_at: string | null;
  returned_at: string | null;
}

export interface AssetSummary {
  total: number;
  assigned: number;
  available: number;
  in_maintenance: number;
  lost: number;
  returned: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
}

export async function listAssets(query: { employee_id?: string; status?: string; category?: string } = {}): Promise<Asset[]> {
  return api<Asset[]>("/assets", { query });
}

export async function createAsset(payload: Record<string, unknown>): Promise<{ id: string; name: string; status: string }> {
  return api(`/assets`, { method: "POST", body: payload });
}

export async function assignAsset(assetId: string, employeeId?: string): Promise<{ id: string; status: string; employee_id: string | null }> {
  return api(`/assets/${assetId}/assign`, { method: "POST", body: { employee_id: employeeId } });
}

export async function updateAssetStatus(assetId: string, status: string, notes?: string): Promise<{ id: string; status: string }> {
  return api(`/assets/${assetId}/status`, { method: "POST", body: { status, notes } });
}

export async function getAssetSummary(): Promise<AssetSummary> {
  return api<AssetSummary>("/assets/summary");
}

// ---------------------------------------------------------------- offboarding

export interface OffboardingTask {
  id: string;
  title: string;
  category: string;
  status: string;
  completed_by?: string | null;
  completed_at?: string | null;
  notes?: string | null;
}

export interface OffboardingItem {
  id: string;
  employee_id: string;
  employee_name: string | null;
  designation: string | null;
  reason: string | null;
  resignation_date: string | null;
  exit_date: string | null;
  status: string;
  initiated_by?: string | null;
  completed_at: string | null;
  knowledge_transfer?: string[];
  exit_interview?: Record<string, unknown> | null;
  transitions_to_alumni: boolean;
  tasks: OffboardingTask[];
}

export interface AlumniProfile {
  id: string;
  employee_id: string;
  name: string | null;
  designation: string | null;
  left_at: string | null;
  reason: string | null;
  status: string;
  linkedin: string | null;
  keep_in_touch: boolean;
  knowledge_contributions: string[];
  last_activity: string | null;
}

export async function listOffboardings(status?: string): Promise<OffboardingItem[]> {
  return api<OffboardingItem[]>("/offboarding", { query: { status } });
}

export async function startOffboarding(payload: Record<string, unknown>): Promise<{ id: string; status: string; employee_id: string }> {
  return api(`/offboarding`, { method: "POST", body: payload });
}

export async function getOffboarding(offboardingId: string): Promise<OffboardingItem> {
  return api<OffboardingItem>(`/offboarding/${offboardingId}`);
}

export async function addOffboardingTask(offboardingId: string, payload: Record<string, unknown>): Promise<{ id: string; title: string; status: string }> {
  return api(`/offboarding/${offboardingId}/tasks`, { method: "POST", body: payload });
}

export async function completeOffboardingTask(offboardingId: string, taskId: string, notes?: string): Promise<{ id: string; status: string }> {
  return api(`/offboarding/${offboardingId}/tasks/${taskId}/complete`, { method: "POST", body: { notes } });
}

export async function submitExitInterview(offboardingId: string, payload: Record<string, unknown>): Promise<{ id: string; exit_interview_completed: boolean }> {
  return api(`/offboarding/${offboardingId}/exit-interview`, { method: "POST", body: payload });
}

export async function completeOffboarding(offboardingId: string): Promise<{ id: string; status: string; alumni_transitioned: boolean }> {
  return api(`/offboarding/${offboardingId}/complete`, { method: "POST" });
}

export async function listAlumni(status?: string): Promise<AlumniProfile[]> {
  return api<AlumniProfile[]>("/offboarding/alumni/list", { query: { status } });
}

export async function updateAlumni(alumniId: string, payload: Record<string, unknown>): Promise<{ id: string; status: string }> {
  return api(`/offboarding/alumni/${alumniId}`, { method: "PATCH", body: payload });
}

export async function markAlumniBoomerang(alumniId: string): Promise<{ id: string; status: string }> {
  return api(`/offboarding/alumni/${alumniId}/boomerang`, { method: "POST" });
}

// ---------------------------------------------------------------- compliance

export interface ComplianceDocument {
  id: string;
  employee_id: string | null;
  employee_name: string | null;
  document_type: string;
  title: string;
  status: string;
  reference: string | null;
  issued_at: string | null;
  expires_at: string | null;
  last_reviewed_at: string | null;
  notes: string | null;
}

export interface TrainingRequirement {
  id: string;
  name: string;
  category: string;
  required_for: string[];
  frequency_days: number;
  description: string | null;
}

export interface TrainingCompletion {
  id: string;
  employee_id: string;
  employee_name: string | null;
  requirement_id: string;
  requirement: string | null;
  category: string | null;
  completed_at: string | null;
  expires_at: string | null;
  expired: boolean;
  provider: string | null;
  certificate_ref: string | null;
}

export interface ComplianceOverview {
  documents: {
    total: number;
    expired: number;
    expiring_30: number;
    expiring_60: number;
    expiring_90: number;
    valid: number;
    missing: number;
    by_type: Record<string, number>;
  };
  trainings: { total_completions: number; expired_completions: number; missing: number };
  urgent: {
    expired_documents: ComplianceDocument[];
    expiring_30_days: ComplianceDocument[];
    missing_trainings: { employee_id: string; employee_name: string; requirement_id: string; requirement: string; category: string; last_completed: string | null }[];
  };
}

export async function listComplianceDocuments(query: { employee_id?: string; document_type?: string; status?: string } = {}): Promise<ComplianceDocument[]> {
  return api<ComplianceDocument[]>("/compliance/documents", { query });
}

export async function recordComplianceDocument(payload: Record<string, unknown>): Promise<{ id: string; title: string; status: string }> {
  return api(`/compliance/documents`, { method: "POST", body: payload });
}

export async function renewComplianceDocument(recordId: string, payload: Record<string, unknown> = {}): Promise<{ id: string; status: string }> {
  return api(`/compliance/documents/${recordId}/renew`, { method: "POST", body: payload });
}

export async function listTrainingRequirements(): Promise<TrainingRequirement[]> {
  return api<TrainingRequirement[]>("/compliance/requirements");
}

export async function createTrainingRequirement(payload: Record<string, unknown>): Promise<{ id: string; name: string }> {
  return api(`/compliance/requirements`, { method: "POST", body: payload });
}

export async function completeTraining(payload: Record<string, unknown>): Promise<{ id: string; requirement_id: string; completed_at: string | null }> {
  return api(`/compliance/trainings`, { method: "POST", body: payload });
}

export async function listTrainingCompletions(employeeId?: string): Promise<TrainingCompletion[]> {
  return api<TrainingCompletion[]>("/compliance/trainings", { query: { employee_id: employeeId } });
}

export async function getComplianceOverview(): Promise<ComplianceOverview> {
  return api<ComplianceOverview>("/compliance/overview");
}

// ---------------------------------------------------------------- workforce

export interface WorkforcePlan {
  id: string;
  title: string;
  horizon: string;
  department: string | null;
  headcount_target: number;
  skill_needs: string[];
  budget: number | null;
  status: string;
  notes: string | null;
}

export interface SuccessionCandidate {
  id: string;
  position_title: string;
  employee_id: string | null;
  candidate_employee_id: string;
  candidate_name: string | null;
  candidate_designation: string | null;
  readiness: number;
  status: string;
  rationale: string | null;
  last_updated_at: string | null;
}

export interface WorkforceSnapshot {
  id: string;
  date: string;
  headcount: number;
  hires_month: number;
  exits_month: number;
  attrition_rate: number;
  departments?: Record<string, { count: number; open_roles: number }>;
}

export interface HiringNeeds {
  by_department: { department: string; open_positions: number; plan_growth: number; priority: string }[];
  total_open_positions: number;
  attrition_rate: number;
  attrition_pressure: boolean;
  last_snapshot_date: string | null;
}

export interface WorkforceAnalytics {
  headcount: number;
  hires_month: number;
  exits_month: number;
  attrition_rate: number;
  trend: { date: string; headcount: number; hires: number; exits: number; attrition: number }[];
  succession_pipeline: { total: number; ready: number; developing: number };
  hiring_needs: HiringNeeds;
  headcount_status: { active: number; total: number };
}

export async function listWorkforcePlans(status?: string): Promise<WorkforcePlan[]> {
  return api<WorkforcePlan[]>("/workforce/plans", { query: { status } });
}

export async function createWorkforcePlan(payload: Record<string, unknown>): Promise<{ id: string; title: string; status: string }> {
  return api(`/workforce/plans`, { method: "POST", body: payload });
}

export async function updateWorkforcePlan(planId: string, payload: Record<string, unknown>): Promise<{ id: string; status: string }> {
  return api(`/workforce/plans/${planId}`, { method: "PATCH", body: payload });
}

export async function listSuccessionCandidates(positionTitle?: string): Promise<SuccessionCandidate[]> {
  return api<SuccessionCandidate[]>("/workforce/succession", { query: { position_title: positionTitle } });
}

export async function addSuccessionCandidate(payload: Record<string, unknown>): Promise<{ id: string; position_title: string; status: string }> {
  return api(`/workforce/succession`, { method: "POST", body: payload });
}

export async function updateSuccessionCandidate(candidateId: string, payload: Record<string, unknown>): Promise<{ id: string; readiness: number; status: string }> {
  return api(`/workforce/succession/${candidateId}`, { method: "PATCH", body: payload });
}

export async function computeWorkforceSnapshot(): Promise<{ id: string; date: string; headcount: number; hires_month: number; exits_month: number; attrition_rate: number }> {
  return api(`/workforce/snapshots`, { method: "POST" });
}

export async function listWorkforceSnapshots(limit = 12): Promise<WorkforceSnapshot[]> {
  return api<WorkforceSnapshot[]>("/workforce/snapshots", { query: { limit } });
}

export async function getWorkforceAnalytics(): Promise<WorkforceAnalytics> {
  return api<WorkforceAnalytics>("/workforce/analytics");
}

export async function getHiringNeeds(): Promise<HiringNeeds> {
  return api<HiringNeeds>("/workforce/hiring-needs");
}

// ---------------------------------------------------------------- wellbeing

export interface WellbeingCheck {
  id: string;
  employee_id?: string;
  employee_name?: string | null;
  check_date: string;
  risk_level: string;
  signals: string[];
  metrics?: Record<string, unknown>;
  notes?: string | null;
  reviewed?: boolean;
}

export interface WellbeingOverview {
  total_checks: number;
  low: number;
  medium: number;
  high: number;
  at_risk_employees: number;
  latest_high: WellbeingCheck[];
}

export async function createWellbeingCheckIn(payload: Record<string, unknown>): Promise<{ id: string; check_date: string; risk_level: string; signals: string[] }> {
  return api(`/wellbeing/check-ins`, { method: "POST", body: payload });
}

export async function myWellbeingChecks(): Promise<WellbeingCheck[]> {
  return api<WellbeingCheck[]>("/wellbeing/my");
}

export async function listWellbeingChecks(query: { risk_level?: string; limit?: number } = {}): Promise<WellbeingCheck[]> {
  return api<WellbeingCheck[]>("/wellbeing", { query });
}

export async function getWellbeingOverview(): Promise<WellbeingOverview> {
  return api<WellbeingOverview>("/wellbeing/overview");
}

export async function getWellbeingRecommendations(): Promise<{ priority: string; title: string; description: string }[]> {
  return api(`/wellbeing/recommendations`);
}

// ---------------------------------------------------------------- payroll

export interface PayrollProvider {
  id: string;
  name: string;
  provider: string;
  is_active: boolean;
}

export interface PayrollRun {
  id: string;
  provider_id: string | null;
  provider_name: string | null;
  provider_vendor: string | null;
  period_start: string | null;
  period_end: string | null;
  status: string;
  employee_count: number;
  gross_amount: number;
  reference_id: string | null;
  synced_at: string | null;
}

export interface PayrollOverview {
  providers: number;
  active_providers: number;
  runs: { total: number; synced: number; pending: number; failed: number };
  last_run: PayrollRun | null;
  latest_synced_gross: number;
}

export async function listPayrollProviders(activeOnly = false): Promise<PayrollProvider[]> {
  return api<PayrollProvider[]>("/payroll/providers", { query: { active_only: activeOnly } });
}

export async function createPayrollProvider(payload: Record<string, unknown>): Promise<{ id: string; name: string; provider: string }> {
  return api(`/payroll/providers`, { method: "POST", body: payload });
}

export async function updatePayrollProvider(providerId: string, payload: Record<string, unknown>): Promise<{ id: string; is_active: boolean }> {
  return api(`/payroll/providers/${providerId}`, { method: "PATCH", body: payload });
}

export async function listPayrollRuns(query: { provider_id?: string; status?: string; limit?: number } = {}): Promise<PayrollRun[]> {
  return api<PayrollRun[]>("/payroll/runs", { query });
}

export async function createPayrollRun(payload: Record<string, unknown>): Promise<{ id: string; status: string; reference_id: string | null }> {
  return api(`/payroll/runs`, { method: "POST", body: payload });
}

export async function markPayrollRunSynced(runId: string, referenceId?: string): Promise<{ id: string; status: string }> {
  return api(`/payroll/runs/${runId}/synced`, { method: "POST", body: { reference_id: referenceId } });
}

export async function markPayrollRunFailed(runId: string): Promise<{ id: string; status: string }> {
  return api(`/payroll/runs/${runId}/failed`, { method: "POST" });
}

export async function getPayrollOverview(): Promise<PayrollOverview> {
  return api<PayrollOverview>("/payroll/overview");
}

// ---------------------------------------------------------------- customers

export interface Customer {
  id: string;
  company_name: string;
  status: string;
  segment: string;
  tier: string;
  industry: string | null;
  website: string | null;
  country: string | null;
  timezone: string;
  employee_count: number | null;
  source: string;
  owner_id: string | null;
  owner_name?: string | null;
  description: string | null;
  health_score: number;
  health_status: string;
  annual_value: number | null;
  last_activity_at: string | null;
  first_contact_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  tags?: { id: string; name: string; color: string }[] | string[];
  contacts?: CustomerContact[];
  notes?: CustomerNote[];
  projects?: { id: string; project_id: string; kind: string; status: string }[];
  meetings?: { id: string; meeting_id: string; kind: string }[];
  documents?: { id: string; document_id: string; kind: string }[];
  account_team?: { id: string; member_id: string; role: string }[];
  contact_count?: number;
  note_count?: number;
  project_count?: number;
  meeting_count?: number;
  document_count?: number;
  health?: {
    score: number;
    status: string;
    renewal_probability: number | null;
    factors: Record<string, unknown>;
    signals: string[];
    computed_at: string | null;
  } | null;
}

export interface CustomerContact {
  id: string;
  customer_id: string;
  name: string;
  role: string;
  designation: string | null;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  timezone: string | null;
  preferred_language: string | null;
  decision_maker: boolean;
  is_primary: boolean;
  notes: string | null;
  created_at: string | null;
}

export interface CustomerNote {
  id: string;
  customer_id: string;
  author_id: string | null;
  content: string;
  kind: string;
  pinned: boolean;
  created_at: string | null;
}

export interface CustomerRelation {
  id: string;
  customer_id: string;
  target_customer_id: string | null;
  target_company_name?: string | null;
  kind: string;
  strength: string;
  note: string | null;
}

export interface CustomerAddress {
  id: string;
  customer_id: string;
  kind: string;
  line1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  is_primary: boolean;
}

export interface CustomerHealthRow {
  customer_id: string;
  company_name: string;
  score: number;
  status: string;
  renewal_probability: number | null;
  factors: Record<string, unknown>;
  signals: string[];
  computed_at: string | null;
}

export interface CustomerTimelineItem {
  id: string;
  customer_id: string;
  kind: string;
  title: string;
  content: string | null;
  occurred_at: string | null;
}

export interface CustomerDashboard {
  total_customers: number;
  active_customers: number;
  prospects: number;
  by_status: Record<string, number>;
  by_health: Record<string, number>;
  by_tier: Record<string, number>;
  contracts: number;
  health_good: number;
  health_risk: number;
}

export interface CustomerAnalytics {
  growth: Record<string, number>;
  total_customers: number;
  revenue: number;
  top_customers: { customer_id: string; company_name: string; value: number }[];
  support: Record<string, number>;
  health_distribution: Record<string, number>;
  concentration_risk: { top_customer_share: number; customers: number };
  contracts_active: number;
  renewals_due: number;
}

export interface CustomerRenewal {
  id: string;
  title: string;
  customer_id: string | null;
  customer_name?: string | null;
  status: string;
  value: number | null;
  expires_at: string | null;
  renewal_status: string;
  days_left?: number;
}

export async function listCustomers(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Customer[]> {
  return api<Customer[]>("/customers", { query });
}

export async function getCustomer(customerId: string): Promise<Customer> {
  return api<Customer>(`/customers/${customerId}`);
}

export async function createCustomer(payload: Record<string, unknown>): Promise<{ id: string; company_name: string; status: string }> {
  return api(`/customers`, { method: "POST", body: payload });
}

export async function updateCustomer(customerId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/customers/${customerId}`, { method: "PATCH", body: payload });
}

export async function deleteCustomer(customerId: string): Promise<{ ok: boolean }> {
  return api(`/customers/${customerId}`, { method: "DELETE" });
}

export async function listCustomerTags(): Promise<{ id: string; name: string; color: string }[]> {
  return api(`/customers/tags`);
}

export async function addCustomerTags(customerId: string, tags: string[]): Promise<{ tags: string[] }> {
  return api(`/customers/${customerId}/tags`, { method: "POST", body: { tags } });
}

export async function removeCustomerTag(customerId: string, tag: string): Promise<{ ok: boolean }> {
  return api(`/customers/${customerId}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" });
}

export async function addCustomerNote(customerId: string, content: string, kind = "note"): Promise<{ id: string }> {
  return api(`/customers/${customerId}/notes`, { method: "POST", body: { content, kind } });
}

export async function listCustomerNotes(customerId: string): Promise<CustomerNote[]> {
  return api<CustomerNote[]>(`/customers/${customerId}/notes`);
}

export async function addCustomerAddress(customerId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/customers/${customerId}/addresses`, { method: "POST", body: payload });
}

export async function listCustomerAddresses(customerId: string): Promise<CustomerAddress[]> {
  return api<CustomerAddress[]>(`/customers/${customerId}/addresses`);
}

export async function deleteCustomerAddress(customerId: string, addressId: string): Promise<{ ok: boolean }> {
  return api(`/customers/${customerId}/addresses/${addressId}`, { method: "DELETE" });
}

export async function addCustomerRelation(customerId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/customers/${customerId}/relationships`, { method: "POST", body: payload });
}

export async function listCustomerRelations(customerId: string): Promise<CustomerRelation[]> {
  return api<CustomerRelation[]>(`/customers/${customerId}/relationships`);
}

export async function linkCustomerProject(customerId: string, projectId: string): Promise<{ customer_id: string; project_id: string }> {
  return api(`/customers/${customerId}/projects/${projectId}`, { method: "POST" });
}

export async function unlinkCustomerProject(customerId: string, projectId: string): Promise<{ ok: boolean }> {
  return api(`/customers/${customerId}/projects/${projectId}`, { method: "DELETE" });
}

export async function linkCustomerMeeting(customerId: string, meetingId: string): Promise<{ customer_id: string; meeting_id: string }> {
  return api(`/customers/${customerId}/meetings/${meetingId}`, { method: "POST" });
}

export async function linkCustomerDocument(customerId: string, documentId: string): Promise<{ customer_id: string; document_id: string }> {
  return api(`/customers/${customerId}/documents/${documentId}`, { method: "POST" });
}

export async function unlinkCustomerDocument(customerId: string, documentId: string): Promise<{ ok: boolean }> {
  return api(`/customers/${customerId}/documents/${documentId}`, { method: "DELETE" });
}

export async function addCustomerTimeline(customerId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/customers/${customerId}/timeline`, { method: "POST", body: payload });
}

export async function listCustomerTimeline(customerId: string): Promise<CustomerTimelineItem[]> {
  return api<CustomerTimelineItem[]>(`/customers/${customerId}/timeline`);
}

// ---------------------------------------------------------------- leads

export interface Lead {
  id: string;
  company_name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  status: string;
  source: string;
  industry: string | null;
  country: string | null;
  owner_id: string | null;
  score: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export async function listLeads(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Lead[]> {
  return api<Lead[]>("/leads", { query });
}

export async function getLead(leadId: string): Promise<Lead> {
  return api<Lead>(`/leads/${leadId}`);
}

export async function createLead(payload: Record<string, unknown>): Promise<{ id: string; company_name: string }> {
  return api(`/leads`, { method: "POST", body: payload });
}

export async function updateLead(leadId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/leads/${leadId}`, { method: "PATCH", body: payload });
}

export async function deleteLead(leadId: string): Promise<{ ok: boolean }> {
  return api(`/leads/${leadId}`, { method: "DELETE" });
}

export async function listLeadActivities(leadId: string): Promise<{ id: string; kind: string; note: string | null; created_at: string | null }[]> {
  return api(`/leads/${leadId}/activities`);
}

export async function addLeadActivity(leadId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/leads/${leadId}/activities`, { method: "POST", body: payload });
}

// ---------------------------------------------------------------- opportunities

export interface Opportunity {
  id: string;
  customer_id: string | null;
  customer_name?: string | null;
  title: string;
  stage: string;
  probability: number | null;
  value: number | null;
  expected_close_at: string | null;
  owner_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OpportunityPipeline {
  stages: Record<string, { value: number; count: number }>;
  total_value: number;
  total_count: number;
  weighted_value: number;
  won_value?: number;
}

export async function listOpportunities(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Opportunity[]> {
  return api<Opportunity[]>("/opportunities", { query });
}

export async function getOpportunityPipeline(): Promise<OpportunityPipeline> {
  return api<OpportunityPipeline>("/opportunities/pipeline");
}

export async function getOpportunity(opportunityId: string): Promise<Opportunity> {
  return api<Opportunity>(`/opportunities/${opportunityId}`);
}

export async function createOpportunity(payload: Record<string, unknown>): Promise<{ id: string; title: string }> {
  return api(`/opportunities`, { method: "POST", body: payload });
}

export async function updateOpportunity(opportunityId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/opportunities/${opportunityId}`, { method: "PATCH", body: payload });
}

export async function winOpportunity(opportunityId: string): Promise<{ id: string; stage: string }> {
  return api(`/opportunities/${opportunityId}/won`, { method: "POST" });
}

export async function loseOpportunity(opportunityId: string, reason?: string): Promise<{ id: string; stage: string }> {
  return api(`/opportunities/${opportunityId}/lost`, { method: "POST", body: { reason } });
}

export async function deleteOpportunity(opportunityId: string): Promise<{ ok: boolean }> {
  return api(`/opportunities/${opportunityId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------- contracts

export interface Contract {
  id: string;
  customer_id: string | null;
  customer_name?: string | null;
  partner_id?: string | null;
  title: string;
  kind: string;
  status: string;
  renewal_status: string;
  value: number | null;
  currency: string;
  effective_from: string | null;
  expires_at: string | null;
  auto_renew: boolean;
  owner_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export async function listContracts(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Contract[]> {
  return api<Contract[]>("/contracts", { query });
}

export async function getContract(contractId: string): Promise<Contract> {
  return api<Contract>(`/contracts/${contractId}`);
}

export async function createContract(payload: Record<string, unknown>): Promise<{ id: string; title: string }> {
  return api(`/contracts`, { method: "POST", body: payload });
}

export async function updateContract(contractId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/contracts/${contractId}`, { method: "PATCH", body: payload });
}

export async function signContract(contractId: string): Promise<{ id: string; status: string }> {
  return api(`/contracts/${contractId}/sign`, { method: "POST" });
}

export async function deleteContract(contractId: string): Promise<{ ok: boolean }> {
  return api(`/contracts/${contractId}`, { method: "DELETE" });
}

export async function listContractRenewals(): Promise<CustomerRenewal[]> {
  return api<CustomerRenewal[]>("/contracts/renewals");
}

// ---------------------------------------------------------------- support

export interface SupportTicket {
  id: string;
  customer_id: string | null;
  customer_name?: string | null;
  subject: string;
  description: string | null;
  category: string;
  priority: string;
  status: string;
  assignee_id: string | null;
  sla_breach_at: string | null;
  resolved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export async function listTickets(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<SupportTicket[]> {
  return api<SupportTicket[]>("/support/tickets", { query });
}

export async function getTicket(ticketId: string): Promise<SupportTicket> {
  return api<SupportTicket>(`/support/tickets/${ticketId}`);
}

export async function createTicket(payload: Record<string, unknown>): Promise<{ id: string; subject: string; status: string }> {
  return api(`/support/tickets`, { method: "POST", body: payload });
}

export async function updateTicket(ticketId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/support/tickets/${ticketId}`, { method: "PATCH", body: payload });
}

export async function deleteTicket(ticketId: string): Promise<{ ok: boolean }> {
  return api(`/support/tickets/${ticketId}`, { method: "DELETE" });
}

export async function getSupportSummary(): Promise<{ total: number; open: number; escalated: number; overdue: number; by_priority: Record<string, number> }> {
  return api(`/support/summary`);
}

// ---------------------------------------------------------------- partners

export interface Partner {
  id: string;
  name: string;
  kind: string;
  status: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  country: string | null;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export async function listPartners(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Partner[]> {
  return api<Partner[]>("/partners", { query });
}

export async function getPartner(partnerId: string): Promise<Partner> {
  return api<Partner>(`/partners/${partnerId}`);
}

export async function createPartner(payload: Record<string, unknown>): Promise<{ id: string; name: string; kind: string }> {
  return api(`/partners`, { method: "POST", body: payload });
}

export async function updatePartner(partnerId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api(`/partners/${partnerId}`, { method: "PATCH", body: payload });
}

export async function deletePartner(partnerId: string): Promise<{ ok: boolean }> {
  return api(`/partners/${partnerId}`, { method: "DELETE" });
}

export async function getPartnerSummary(): Promise<{ total: number; active: number; by_kind: Record<string, number> }> {
  return api(`/partners/summary`);
}

// ---------------------------------------------------------------- CRM analytics

export async function getCustomerDashboard(): Promise<CustomerDashboard> {
  return api<CustomerDashboard>("/analytics/dashboard");
}

export async function getCustomerAnalytics(): Promise<CustomerAnalytics> {
  return api<CustomerAnalytics>("/analytics/overview");
}

export async function getCustomerHealth(): Promise<CustomerHealthRow[]> {
  return api<CustomerHealthRow[]>("/analytics/health");
}

export async function recomputeCustomerHealth(): Promise<{ updated: number; customers: CustomerHealthRow[] }> {
  return api(`/analytics/health/recompute`, { method: "POST" });
}

export async function getCustomerRenewals(): Promise<{ total_due: number; contracts: CustomerRenewal[]; horizon_days: number }> {
  return api(`/analytics/renewals`);
}

export async function getRelationshipHealth(): Promise<{ relationships: Record<string, unknown>[]; total: number }> {
  return api(`/analytics/relationships`);
}

export async function buildRelationshipGraph(): Promise<{ customers: number; edges: number }> {
  return api(`/analytics/relationships/build`, { method: "POST" });
}

export async function getRelationshipRisks(): Promise<{ single_points_of_failure: Record<string, unknown>[]; total: number }> {
  return api(`/analytics/relationships/risks`);
}

export async function askCustomerAI(question: string): Promise<{ answer: string }> {
  return api(`/analytics/ask`, { method: "POST", body: { question } });
}

// ---------------------------------------------------------------- finance (Phase 13)

export interface Budget {
  id: string;
  name: string;
  budget_type: string;
  department_id: string | null;
  department_name: string | null;
  project_id: string | null;
  project_name: string | null;
  team_id: string | null;
  fiscal_year: number | null;
  period_start: string | null;
  period_end: string | null;
  allocated_amount: number;
  used_amount: number;
  remaining_amount: number;
  usage_pct: number;
  currency: string;
  status: string;
  owner_id: string | null;
  owner_name: string | null;
  forecast_amount: number | null;
  risk_level: string;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BudgetSummary {
  total_budgets: number;
  allocated: number;
  used: number;
  remaining: number;
  usage_pct: number;
  by_type: Record<string, { allocated: number; used: number }>;
  risk_counts: Record<string, number>;
}

export interface Expense {
  id: string;
  employee_id: string | null;
  employee_name: string | null;
  expense_type: string;
  amount: number;
  currency: string;
  incurred_at: string | null;
  merchant: string | null;
  description: string;
  project_id: string | null;
  project_name: string | null;
  budget_id: string | null;
  budget_name: string | null;
  status: string;
  approver_id: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  reimbursed_at: string | null;
  receipt_url: string | null;
  duplicate_of: string | null;
  policy_flags: Record<string, unknown>;
  created_at: string | null;
}

export interface Vendor {
  id: string;
  name: string;
  kind: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  country: string | null;
  tax_id: string | null;
  payment_terms: string | null;
  rating: number | null;
  performance_score: number;
  status: string;
  description: string | null;
  risk?: { level: string; score: number; factors: Record<string, unknown> };
  contracts?: {
    id: string; title: string; value: number | null; currency: string;
    effective_from: string | null; expires_at: string | null; renewal_status: string; status: string;
  }[];
  orders?: { id: string; po_number: string; title: string; total_amount: number; status: string }[];
  invoices?: { id: string; invoice_number: string | null; title: string; amount: number; status: string; due_at: string | null }[];
  payments?: { id: string; amount: number; method: string; status: string; paid_at: string | null }[];
  total_spend?: number;
}

export interface VendorSummary {
  total: number;
  active: number;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
  high_risk: number;
}

export interface VendorContract {
  id: string;
  vendor_id: string | null;
  vendor_name: string | null;
  title: string;
  value: number | null;
  currency: string;
  effective_from: string | null;
  expires_at: string | null;
  days_left: number | null;
  renewal_status: string;
  auto_renew: boolean;
  status: string;
  notes: string | null;
  created_at: string | null;
}

export interface Invoice {
  id: string;
  direction: string;
  vendor_id: string | null;
  vendor_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  project_id: string | null;
  project_name: string | null;
  invoice_number: string | null;
  reference_number: string | null;
  title: string;
  amount: number;
  tax_amount: number;
  currency: string;
  issued_at: string | null;
  due_at: string | null;
  status: string;
  paid_at: string | null;
  payment_reference: string | null;
  external_system: string | null;
  external_id: string | null;
  synced_at: string | null;
  created_at: string | null;
}

export interface InvoiceSummary {
  total: number;
  payable: { count: number; due: number; paid: number; overdue: number };
  receivable: { count: number; due: number; paid: number; overdue: number };
  overdue: number;
}

export interface Payment {
  id: string;
  invoice_id: string | null;
  vendor_id: string | null;
  amount: number;
  currency: string;
  method: string;
  status: string;
  paid_at: string | null;
  reference: string | null;
  external_id: string | null;
  created_at: string | null;
}

export interface PurchaseRequest {
  id: string;
  employee_id: string | null;
  employee_name: string | null;
  title: string;
  description: string | null;
  category: string;
  quantity: number;
  estimated_cost: number | null;
  currency: string;
  vendor_name: string | null;
  vendor_id: string | null;
  vendor_label: string | null;
  project_id: string | null;
  project_name: string | null;
  budget_id: string | null;
  budget_name: string | null;
  status: string;
  approver_id: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  policy_flags: Record<string, unknown>;
  created_at: string | null;
}

export interface PurchaseOrder {
  id: string;
  purchase_request_id: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  project_id: string | null;
  project_name: string | null;
  po_number: string;
  title: string;
  total_amount: number;
  currency: string;
  status: string;
  issued_at: string | null;
  expected_delivery_at: string | null;
  delivered_at: string | null;
  external_reference: string | null;
  created_at: string | null;
}

export interface FinancialForecast {
  id: string;
  kind: string;
  horizon_months: number;
  period_start: string | null;
  period_end: string | null;
  forecast_data: Record<string, unknown>;
  confidence: number;
  generated_by: string;
  status: string;
  created_at: string | null;
}

export interface FinanceIntegration {
  id: string;
  provider: string;
  name: string;
  integration_type: string;
  status: string;
  config: Record<string, unknown>;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string | null;
}

export interface FinanceDashboard {
  total_budgets: number;
  budget_allocated: number;
  budget_used: number;
  budget_remaining: number;
  budget_usage_pct: number;
  expense_total: number;
  operating_costs: number;
  pending_approvals: number;
  payable_due: number;
  receivable_due: number;
  total_paid: number;
  revenue: number;
  costs: number;
  overdue_invoices: number;
  open_purchase_requests: number;
  purchase_orders: number;
  vendors: number;
  high_risk_budgets: number;
}

export interface RiskItem {
  id: string;
  type: string;
  severity: string;
  message: string;
  entity_type: string;
  entity_id: string;
  value: number;
}

export interface RiskSummary {
  total: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  health_score: number;
  risks: RiskItem[];
}

export interface FinanceAiReply {
  reply: string;
  intent: string;
  data?: Record<string, unknown>;
}

// ---------------------------------------------------------------- finance API

export async function getFinanceDashboard(): Promise<FinanceDashboard> {
  return api<FinanceDashboard>("/finance/analytics/dashboard");
}

export async function getFinanceMetrics(metricType?: string): Promise<FinancialMetric[]> {
  const query = metricType ? { metric_type: metricType } : undefined;
  return api(`/finance/analytics/metrics`, { query });
}

export interface FinancialMetric {
  id: string;
  metric_type: string;
  period: string;
  value: number;
  payload?: Record<string, unknown>;
  created_at?: string | null;
}

export async function scanFinanceRisks(): Promise<{ total: number; risks: RiskItem[] }> {
  return api(`/finance/risks/scan`, { method: "POST" });
}

export async function getRiskSummary(): Promise<RiskSummary> {
  return api<RiskSummary>("/finance/risks/summary");
}

export async function listBudgets(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Budget[]> {
  return api<Budget[]>("/finance/budgets", { query });
}

export async function getBudgetSummary(): Promise<BudgetSummary> {
  return api<BudgetSummary>("/finance/budgets/summary");
}

export async function getBudget(budgetId: string): Promise<Budget> {
  return api<Budget>(`/finance/budgets/${budgetId}`);
}

export async function createBudget(payload: Record<string, unknown>): Promise<Budget> {
  return api<Budget>("/finance/budgets", { method: "POST", body: payload });
}

export async function updateBudget(budgetId: string, payload: Record<string, unknown>): Promise<Budget> {
  return api<Budget>(`/finance/budgets/${budgetId}`, { method: "PATCH", body: payload });
}

export async function deleteBudget(budgetId: string): Promise<{ deleted: string }> {
  return api(`/finance/budgets/${budgetId}`, { method: "DELETE" });
}

export async function listExpenses(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Expense[]> {
  return api<Expense[]>("/finance/expenses", { query });
}

export async function createExpense(payload: Record<string, unknown>): Promise<Expense> {
  return api<Expense>("/finance/expenses", { method: "POST", body: payload });
}

export async function decideExpense(expenseId: string, decision: string, note?: string): Promise<Expense> {
  return api<Expense>(`/finance/expenses/${expenseId}/decide`, { method: "POST", body: { decision, note } });
}

export async function listVendors(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Vendor[]> {
  return api<Vendor[]>("/finance/vendors", { query });
}

export async function getVendorSummary(): Promise<VendorSummary> {
  return api<VendorSummary>("/finance/vendors/summary");
}

export async function getVendor(vendorId: string): Promise<Vendor> {
  return api<Vendor>(`/finance/vendors/${vendorId}`);
}

export async function createVendor(payload: Record<string, unknown>): Promise<Vendor> {
  return api<Vendor>("/finance/vendors", { method: "POST", body: payload });
}

export async function listVendorContracts(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<VendorContract[]> {
  return api<VendorContract[]>("/finance/vendor-contracts", { query });
}

export async function createVendorContract(payload: Record<string, unknown>): Promise<VendorContract> {
  return api<VendorContract>("/finance/vendor-contracts", { method: "POST", body: payload });
}

export async function renewVendorContract(contractId: string, payload: Record<string, unknown>): Promise<VendorContract> {
  return api<VendorContract>(`/finance/vendor-contracts/${contractId}/renew`, { method: "POST", body: payload });
}

export async function listInvoices(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Invoice[]> {
  return api<Invoice[]>("/finance/invoices", { query });
}

export async function getInvoiceSummary(): Promise<InvoiceSummary> {
  return api<InvoiceSummary>("/finance/invoices/summary");
}

export async function createInvoice(payload: Record<string, unknown>): Promise<Invoice> {
  return api<Invoice>("/finance/invoices", { method: "POST", body: payload });
}

export async function markInvoicesOverdue(): Promise<{ marked_overdue: number }> {
  return api(`/finance/invoices/mark-overdue`, { method: "POST" });
}

export async function listPayments(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<Payment[]> {
  return api<Payment[]>("/finance/payments", { query });
}

export async function createPayment(payload: Record<string, unknown>): Promise<Payment> {
  return api<Payment>("/finance/payments", { method: "POST", body: payload });
}

export async function listPurchaseRequests(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<PurchaseRequest[]> {
  return api<PurchaseRequest[]>("/finance/requests", { query });
}

export async function createPurchaseRequest(payload: Record<string, unknown>): Promise<PurchaseRequest> {
  return api<PurchaseRequest>("/finance/requests", { method: "POST", body: payload });
}

export async function decidePurchaseRequest(requestId: string, decision: string, note?: string): Promise<PurchaseRequest> {
  return api<PurchaseRequest>(`/finance/requests/${requestId}/decide`, { method: "POST", body: { decision, note } });
}

export async function listPurchaseOrders(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<PurchaseOrder[]> {
  return api<PurchaseOrder[]>("/finance/purchase-orders", { query });
}

export async function createPurchaseOrder(payload: Record<string, unknown>): Promise<PurchaseOrder> {
  return api<PurchaseOrder>("/finance/purchase-orders", { method: "POST", body: payload });
}

export async function updatePurchaseOrder(orderId: string, payload: Record<string, unknown>): Promise<PurchaseOrder> {
  return api<PurchaseOrder>(`/finance/purchase-orders/${orderId}`, { method: "PATCH", body: payload });
}

export async function generateForecasts(payload: Record<string, unknown>): Promise<{ generated: FinancialForecast[] }> {
  return api(`/finance/forecasts/generate`, { method: "POST", body: payload });
}

export async function listForecasts(query: Record<string, string | number | boolean | null | undefined> = {}): Promise<FinancialForecast[]> {
  return api<FinancialForecast[]>("/finance/forecasts", { query });
}

export async function listIntegrations(): Promise<FinanceIntegration[]> {
  return api<FinanceIntegration[]>("/finance/integrations");
}

export async function getIntegrationsHealth(): Promise<{ connected: number; syncing: number; error: number; total: number }> {
  return api(`/finance/integrations/health`);
}

export async function createIntegration(payload: Record<string, unknown>): Promise<FinanceIntegration> {
  return api<FinanceIntegration>("/finance/integrations", { method: "POST", body: payload });
}

export async function syncIntegration(integrationId: string, dryRun = false): Promise<Record<string, unknown>> {
  return api(`/finance/integrations/${integrationId}/sync`, { method: "POST", body: { dry_run: dryRun } });
}

export async function importFinanceCsv(kind: string, content: string): Promise<{ imported: number; errors: number }> {
  return api(`/finance/integrations/import`, { method: "POST", body: { kind, content } });
}

export async function askFinanceAi(message: string): Promise<FinanceAiReply> {
  return api<FinanceAiReply>("/finance/ask", { method: "POST", body: { message } });
}

// ------------------------------------------------------------- enterprise (Phase 15)

export interface IdentityProvider {
  id: string;
  provider_type: string;
  name: string;
  description: string | null;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface IdentityBinding {
  id: string;
  user_id: string;
  external_subject: string;
  provider: string;
  mfa_enabled: boolean;
  mfa_method: string | null;
  status: string;
  last_login_at: string | null;
  created_at: string | null;
}

export interface TrustedDevice {
  id: string;
  user_id: string;
  name: string;
  device_type: string;
  trusted: boolean;
  verified_at: string | null;
  last_seen_at: string | null;
  created_at: string | null;
}

export interface AuthPolicy {
  id: string;
  name: string;
  mfa_required: boolean;
  passkey_required: boolean;
  password_policy: Record<string, unknown>;
  session_timeout_minutes: number;
  ip_restrictions: string[];
  enabled: boolean;
  created_at: string | null;
}

export interface ScimUserResource {
  schemas?: string[];
  id: string;
  userName: string;
  externalId?: string;
  active: boolean;
  emails?: { value: string; primary?: boolean }[];
  meta?: Record<string, unknown>;
}

export interface ScimGroupResource {
  id: string;
  displayName: string;
  members: { value: string; type: string }[];
}

export interface Plugin {
  id: string;
  plugin_key: string;
  name: string;
  description: string | null;
  version: string;
  author: string | null;
  category: string;
  status: string;
  sandbox: boolean;
  verified: boolean;
  scan_status: string;
  requested_permissions: string[];
  settings: Record<string, unknown>;
  installed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface MarketplaceItem {
  id: string;
  plugin_key: string;
  name: string;
  description: string | null;
  category: string;
  price: number;
  rating: number;
  review_count: number;
  downloads: number;
  version: string;
  verified: boolean;
  scanned: boolean;
  published: boolean;
  manifest: Record<string, unknown>;
  created_at: string | null;
}

export interface ApiKeyRow {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  rate_limit_per_minute: number;
  status: string;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string | null;
  key?: string;
}

export interface GatewayVersionInfo {
  versions: string[];
  auth_header: string;
  default_rate_limit_per_minute: number;
}

export interface IntegrationConnection {
  id: string;
  name: string;
  provider: string;
  kind: string;
  config: Record<string, unknown>;
  auth_type: string;
  status: string;
  connected_at: string | null;
  last_sync_at: string | null;
  error: string | null;
  created_at: string | null;
}

export interface SystemMetric {
  id: string;
  name: string;
  value: number;
  unit: string | null;
  tags: Record<string, unknown>;
  recorded_at: string;
  created_at: string | null;
}

export interface MonitoringHealth {
  status: string;
  checks: Record<string, { value: number | null; threshold?: number }>;
  recorded_at: string;
}

export interface MonitoringAlert {
  severity: string;
  name: string;
  value: number;
  message: string;
}

export interface ObservabilityLog {
  id: string;
  level: string;
  source: string;
  message: string;
  details: Record<string, unknown>;
  trace_id: string | null;
  span_id: string | null;
  recorded_at: string;
  created_at: string | null;
}

export interface SecurityEvent {
  id: string;
  event_type: string;
  severity: string;
  title: string;
  actor_id: string | null;
  source_ip: string | null;
  details: Record<string, unknown>;
  status: string;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string | null;
}

export interface SecurityRules {
  event_types: string[];
  brute_force_threshold: number;
  brute_force_window_minutes: number;
}

export interface ComplianceControl {
  id: string;
  framework: string;
  control: string;
  title: string;
  status: string;
  evidence: Record<string, unknown>;
  notes: string | null;
  owner_id: string | null;
  checked_at: string | null;
  due_at: string | null;
  created_at: string | null;
}

export interface ComplianceReport {
  frameworks: Record<string, Record<string, number>>;
  overall_score: number;
  [key: string]: unknown;
}

export interface OrganizationLicense {
  id: string;
  plan: string;
  seats: number;
  features: string[];
  status: string;
  started_at: string | null;
  expires_at: string | null;
  created_at: string | null;
}

export interface FeatureFlag {
  id: string;
  key: string;
  name: string;
  description: string | null;
  enabled: boolean;
  rules: Record<string, unknown>;
  updated_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AiModelInfo {
  model: string;
  tier: string;
  [key: string]: unknown;
}

export interface EnterpriseOverview {
  organization_id: string;
  identity_providers: number;
  installed_plugins: number;
  active_api_keys: number;
  active_integrations: number;
  open_security_events: number;
  enabled_feature_flags: number;
  metric_samples: number;
  license: OrganizationLicense;
}

// ---------------------------------------------------------------- identity & SSO

export async function listIdentityProviders(): Promise<IdentityProvider[]> {
  return api<IdentityProvider[]>("/enterprise/identity/providers");
}

export async function createIdentityProvider(payload: Record<string, unknown>): Promise<IdentityProvider> {
  return api<IdentityProvider>("/enterprise/identity/providers", { method: "POST", body: payload });
}

export async function updateIdentityProvider(providerId: string, payload: Record<string, unknown>): Promise<IdentityProvider> {
  return api<IdentityProvider>(`/enterprise/identity/providers/${providerId}`, { method: "PATCH", body: payload });
}

export async function deleteIdentityProvider(providerId: string): Promise<void> {
  return api(`/enterprise/identity/providers/${providerId}`, { method: "DELETE" });
}

export async function listIdentityBindings(): Promise<IdentityBinding[]> {
  return api<IdentityBinding[]>("/enterprise/identity/bindings");
}

export async function enrollMfa(): Promise<{ mfa_method: string; mfa_secret: string; mfa_enabled: boolean }> {
  return api("/enterprise/identity/mfa/enroll", { method: "POST" });
}

export async function verifyMfa(code: string): Promise<{ mfa_enabled: boolean }> {
  return api("/enterprise/identity/mfa/verify", { method: "POST", body: { code } });
}

export async function registerPasskey(credentialId: string): Promise<{ passkeys: string[] }> {
  return api("/enterprise/identity/passkeys", { method: "POST", body: { credential_id: credentialId } });
}

export async function listDevices(): Promise<TrustedDevice[]> {
  return api<TrustedDevice[]>("/enterprise/identity/devices");
}

export async function trustDevice(payload: Record<string, unknown>): Promise<TrustedDevice> {
  return api<TrustedDevice>("/enterprise/identity/devices", { method: "POST", body: payload });
}

export async function getAuthPolicy(): Promise<{ policy: AuthPolicy | null }> {
  return api("/enterprise/identity/policies");
}

export async function createAuthPolicy(payload: Record<string, unknown>): Promise<AuthPolicy> {
  return api<AuthPolicy>("/enterprise/identity/policies", { method: "POST", body: payload });
}

export async function ssoInitiate(providerId: string, redirectUri = "/"): Promise<Record<string, unknown>> {
  return api("/enterprise/sso/initiate", { method: "POST", body: { provider_id: providerId, redirect_uri: redirectUri } });
}

export async function ssoComplete(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return api("/enterprise/sso/complete", { method: "POST", body: payload });
}

// ------------------------------------------------------------------------- SCIM

export async function scimListUsers(): Promise<{ totalResults: number; Resources: ScimUserResource[] }> {
  return api("/enterprise/scim/users");
}

export async function scimCreateUser(payload: Record<string, unknown>): Promise<ScimUserResource> {
  return api<ScimUserResource>("/enterprise/scim/users", { method: "POST", body: payload });
}

export async function scimUpdateUser(externalId: string, payload: Record<string, unknown>): Promise<ScimUserResource> {
  return api<ScimUserResource>(`/enterprise/scim/users/${externalId}`, { method: "PATCH", body: payload });
}

export async function scimDeleteUser(externalId: string): Promise<void> {
  return api(`/enterprise/scim/users/${externalId}`, { method: "DELETE" });
}

export async function scimListGroups(): Promise<{ totalResults: number; Resources: ScimGroupResource[] }> {
  return api("/enterprise/scim/groups");
}

export async function scimCreateGroup(payload: Record<string, unknown>): Promise<ScimGroupResource> {
  return api<ScimGroupResource>("/enterprise/scim/groups", { method: "POST", body: payload });
}

export async function scimDeleteGroup(externalId: string): Promise<void> {
  return api(`/enterprise/scim/groups/${externalId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------- plugins

export async function listPlugins(status?: string): Promise<Plugin[]> {
  return api<Plugin[]>("/enterprise/plugins", { query: { status } });
}

export async function installPlugin(payload: Record<string, unknown>): Promise<Plugin> {
  return api<Plugin>("/enterprise/plugins", { method: "POST", body: payload });
}

export async function getPlugin(pluginId: string): Promise<Plugin> {
  return api<Plugin>(`/enterprise/plugins/${pluginId}`);
}

export async function enablePlugin(pluginId: string): Promise<Plugin> {
  return api<Plugin>(`/enterprise/plugins/${pluginId}/enable`, { method: "POST" });
}

export async function disablePlugin(pluginId: string): Promise<Plugin> {
  return api<Plugin>(`/enterprise/plugins/${pluginId}/disable`, { method: "POST" });
}

export async function updatePlugin(pluginId: string, payload: Record<string, unknown>): Promise<Plugin> {
  return api<Plugin>(`/enterprise/plugins/${pluginId}/update`, { method: "POST", body: payload });
}

export async function updatePluginSettings(pluginId: string, settings: Record<string, unknown>): Promise<Plugin> {
  return api<Plugin>(`/enterprise/plugins/${pluginId}/settings`, { method: "PATCH", body: { settings } });
}

export async function removePlugin(pluginId: string): Promise<void> {
  return api(`/enterprise/plugins/${pluginId}`, { method: "DELETE" });
}

// -------------------------------------------------------------------- marketplace

export async function listMarketplaceItems(category?: string, search?: string): Promise<MarketplaceItem[]> {
  return api<MarketplaceItem[]>("/enterprise/marketplace/items", { query: { category, search } });
}

export async function getMarketplaceItem(itemId: string): Promise<MarketplaceItem> {
  return api<MarketplaceItem>(`/enterprise/marketplace/items/${itemId}`);
}

export async function publishMarketplaceItem(payload: Record<string, unknown>): Promise<MarketplaceItem> {
  return api<MarketplaceItem>("/enterprise/marketplace/items", { method: "POST", body: payload });
}

export async function reviewMarketplaceItem(itemId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return api(`/enterprise/marketplace/items/${itemId}/reviews`, { method: "POST", body: payload });
}

export async function installMarketplaceItem(itemId: string): Promise<Plugin> {
  return api<Plugin>(`/enterprise/marketplace/items/${itemId}/install`, { method: "POST" });
}

export async function updateMarketplaceItem(itemId: string, payload: Record<string, unknown>): Promise<MarketplaceItem> {
  return api<MarketplaceItem>(`/enterprise/marketplace/items/${itemId}`, { method: "PATCH", body: payload });
}

// -------------------------------------------------------------------- API gateway

export async function listApiKeys(status?: string): Promise<ApiKeyRow[]> {
  return api<ApiKeyRow[]>("/enterprise/api-keys", { query: { status } });
}

export async function createApiKey(payload: Record<string, unknown>): Promise<ApiKeyRow> {
  return api<ApiKeyRow>("/enterprise/api-keys", { method: "POST", body: payload });
}

export async function rotateApiKey(keyId: string): Promise<ApiKeyRow> {
  return api<ApiKeyRow>(`/enterprise/api-keys/${keyId}/rotate`, { method: "POST" });
}

export async function revokeApiKey(keyId: string): Promise<void> {
  return api(`/enterprise/api-keys/${keyId}`, { method: "DELETE" });
}

export async function gatewayVersions(): Promise<GatewayVersionInfo> {
  return api<GatewayVersionInfo>("/enterprise/gateway/versions");
}

export async function gatewayCheck(apiKey: string): Promise<Record<string, unknown>> {
  return api("/enterprise/gateway/check", { method: "POST", body: { api_key: apiKey } });
}

// ------------------------------------------------------------------- integrations

export async function listEnterpriseIntegrations(status?: string): Promise<IntegrationConnection[]> {
  return api<IntegrationConnection[]>("/enterprise/integrations", { query: { status } });
}

export async function createEnterpriseIntegration(payload: Record<string, unknown>): Promise<IntegrationConnection> {
  return api<IntegrationConnection>("/enterprise/integrations", { method: "POST", body: payload });
}

export async function testEnterpriseIntegration(connectionId: string): Promise<Record<string, unknown>> {
  return api(`/enterprise/integrations/${connectionId}/test`, { method: "POST" });
}

export async function syncEnterpriseIntegration(connectionId: string): Promise<Record<string, unknown>> {
  return api(`/enterprise/integrations/${connectionId}/sync`, { method: "POST" });
}

export async function updateIntegration(connectionId: string, payload: Record<string, unknown>): Promise<IntegrationConnection> {
  return api<IntegrationConnection>(`/enterprise/integrations/${connectionId}`, { method: "PATCH", body: payload });
}

export async function deleteIntegration(connectionId: string): Promise<void> {
  return api(`/enterprise/integrations/${connectionId}`, { method: "DELETE" });
}

// ----------------------------------------------------------------- monitoring

export async function monitoringHealth(): Promise<MonitoringHealth> {
  return api<MonitoringHealth>("/enterprise/monitoring/health");
}

export async function listMetrics(name?: string, limit = 100): Promise<SystemMetric[]> {
  return api<SystemMetric[]>("/enterprise/monitoring/metrics", { query: { name, limit } });
}

export async function ingestMetric(payload: Record<string, unknown>): Promise<SystemMetric> {
  return api<SystemMetric>("/enterprise/monitoring/metrics", { method: "POST", body: payload });
}

export async function monitoringAlerts(): Promise<MonitoringAlert[]> {
  return api<MonitoringAlert[]>("/enterprise/monitoring/alerts");
}

// ---------------------------------------------------------------- observability

export async function ingestLog(payload: Record<string, unknown>): Promise<ObservabilityLog> {
  return api<ObservabilityLog>("/enterprise/observability/logs", { method: "POST", body: payload });
}

export async function queryLogs(level?: string, source?: string, search?: string, limit = 50): Promise<ObservabilityLog[]> {
  return api<ObservabilityLog[]>("/enterprise/observability/logs", { query: { level, source, search, limit } });
}

export async function getLog(logId: string): Promise<ObservabilityLog> {
  return api<ObservabilityLog>(`/enterprise/observability/logs/${logId}`);
}

export async function getTrace(traceId: string): Promise<ObservabilityLog[]> {
  return api<ObservabilityLog[]>(`/enterprise/observability/traces/${traceId}`);
}

// ---------------------------------------------------------------------- security

export async function listSecurityEvents(status?: string, severity?: string): Promise<SecurityEvent[]> {
  return api<SecurityEvent[]>("/enterprise/security/events", { query: { status, severity } });
}

export async function recordSecurityEvent(payload: Record<string, unknown>): Promise<SecurityEvent> {
  return api<SecurityEvent>("/enterprise/security/events", { method: "POST", body: payload });
}

export async function detectFailedLogin(email: string, sourceIp: string): Promise<{ event_id: string; failed_count: number; brute_force: boolean }> {
  return api("/enterprise/security/detect/failed-login", { method: "POST", body: { email, source_ip: sourceIp } });
}

export async function resolveSecurityEvent(eventId: string): Promise<SecurityEvent> {
  return api<SecurityEvent>(`/enterprise/security/events/${eventId}/resolve`, { method: "POST" });
}

export async function securityRules(): Promise<SecurityRules> {
  return api<SecurityRules>("/enterprise/security/rules");
}

export async function checkIp(ip: string): Promise<{ allowed: boolean; ip: string }> {
  return api("/enterprise/security/check-ip", { method: "POST", body: { ip } });
}

// --------------------------------------------------------------------- compliance

export async function complianceFrameworks(): Promise<Record<string, string[]>> {
  return api("/enterprise/compliance/frameworks");
}

export async function listComplianceRecords(framework?: string, status?: string): Promise<ComplianceControl[]> {
  return api<ComplianceControl[]>("/enterprise/compliance/records", { query: { framework, status } });
}

export async function upsertComplianceRecord(payload: Record<string, unknown>): Promise<ComplianceControl> {
  return api<ComplianceControl>("/enterprise/compliance/records", { method: "POST", body: payload });
}

export async function updateComplianceRecord(recordId: string, payload: Record<string, unknown>): Promise<ComplianceControl> {
  return api<ComplianceControl>(`/enterprise/compliance/records/${recordId}`, { method: "PATCH", body: payload });
}

export async function complianceReport(): Promise<ComplianceReport> {
  return api<ComplianceReport>("/enterprise/compliance/report");
}

// ----------------------------------------------------------------------- license

export async function getLicense(): Promise<OrganizationLicense> {
  return api<OrganizationLicense>("/enterprise/license");
}

export async function refreshLicense(): Promise<Record<string, unknown>> {
  return api("/enterprise/license/refresh", { method: "POST" });
}

export async function changeLicensePlan(payload: Record<string, unknown>): Promise<OrganizationLicense> {
  return api<OrganizationLicense>("/enterprise/license", { method: "PATCH", body: payload });
}

export async function licensePlans(): Promise<Record<string, unknown>> {
  return api("/enterprise/license/plans");
}

// ------------------------------------------------------------------ feature flags

export async function listFeatureFlags(): Promise<FeatureFlag[]> {
  return api<FeatureFlag[]>("/enterprise/feature-flags");
}

export async function createFeatureFlag(payload: Record<string, unknown>): Promise<FeatureFlag> {
  return api<FeatureFlag>("/enterprise/feature-flags", { method: "POST", body: payload });
}

export async function updateFeatureFlag(flagId: string, payload: Record<string, unknown>): Promise<FeatureFlag> {
  return api<FeatureFlag>(`/enterprise/feature-flags/${flagId}`, { method: "PATCH", body: payload });
}

export async function deleteFeatureFlag(flagId: string): Promise<void> {
  return api(`/enterprise/feature-flags/${flagId}`, { method: "DELETE" });
}

export async function evaluateFeatureFlag(key: string, roles?: string[]): Promise<{ key: string; enabled: boolean; reason: string }> {
  return api("/enterprise/feature-flags/evaluate", { method: "POST", body: { key, roles } });
}

// ---------------------------------------------------------------------------- AI

export async function aiModels(): Promise<AiModelInfo[]> {
  return api<AiModelInfo[]>("/enterprise/ai/models");
}

export async function aiUsage(): Promise<Record<string, unknown>> {
  return api("/enterprise/ai/usage");
}

export async function setAiConsent(scope: string, granted: boolean): Promise<Record<string, unknown>> {
  return api("/enterprise/ai/consent", { method: "POST", body: { scope, granted } });
}

export async function aiMemorySettings(): Promise<Record<string, unknown>> {
  return api("/enterprise/ai/memory");
}

// ------------------------------------------------------------------------ admin

export async function enterpriseOverview(): Promise<EnterpriseOverview> {
  return api<EnterpriseOverview>("/enterprise/admin/overview");
}

// ------------------------------------------------- Phase 17 — Industry Solutions

export interface IndustryPackSummary {
  key: string;
  name: string;
  icon: string | null;
  color: string | null;
  description: string;
  business_types: string[];
  countries: string[];
  modules: string[];
  workflows: string[];
  compliance_frameworks: string[];
  ai_models: string[];
  kpis: string[];
  installed?: string | null;
}

export interface IndustryModule {
  key: string;
  name: string;
  category: string;
  description: string;
  entities: string[];
  permissions: string[];
  enabled?: boolean;
}

export interface IndustryTemplate {
  key: string;
  name: string;
  kind: string;
  description: string | null;
  content: Record<string, unknown>;
  tags: string[];
  default: boolean;
  version: string;
}

export interface IndustryWorkflowTemplate {
  key: string;
  name: string;
  description: string | null;
  steps: { key: string; name: string; assignee_role?: string }[];
}

export interface IndustryComplianceRule {
  policy_id: string;
  policy_key: string;
  name: string;
  framework: string;
  region: string;
  control: string | null;
  severity: string;
  evidence_requirements: string[];
  cadence_days: number;
  enabled: boolean;
  overridable: boolean;
}

export interface IndustryAIModelProfile {
  model_key: string;
  name: string;
  enabled: boolean;
  provider: string;
  terminology: string[];
  knowledge_scope: Record<string, unknown>;
  guardrails: string[];
  skills: string[];
  temperature: number;
}

export interface IndustryKPI {
  key: string;
  name: string;
  unit?: string | null;
  benchmark?: number | null;
}

export interface IndustryMetricCard {
  metric_key: string;
  name: string;
  unit: string | null;
  value: number | null;
  benchmark: number | null;
  status: string;
  delta_pct: number | null;
  points: number;
}

export interface InstalledIndustryPack {
  id: string;
  industry_key: string;
  name: string;
  icon: string | null;
  color: string | null;
  description: string;
  pack_version: string;
  status: string;
  modules_enabled: string[];
  workflows_enabled: string[];
  templates_enabled: string[];
  settings: Record<string, unknown>;
  installed_at: string | null;
  business_types: string[];
  kpis: IndustryKPI[];
  navigation: Record<string, unknown>;
  plugin: { id: string; plugin_key: string; version: string; scan_status: string; status: string } | null;
}

export interface IndustrySelection {
  industry_key: string;
  business_type: string | null;
  company_size: string | null;
  country: string | null;
  regulations: string[];
  role: string;
  status: string;
}

export interface IndustryWorkflowRun {
  id: string;
  template_key: string;
  name: string;
  status: string;
  current_step: string | null;
  progress: number;
  source_workflow_id: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface IndustryCompliancePosture {
  industry_key: string;
  total: number;
  passed: number;
  warned: number;
  failed: number;
  pending: number;
  score: number | null;
}

export interface IndustryPackOverview {
  industry_key: string;
  installed: boolean;
  status: string;
  modules: IndustryModule[];
  workflows: IndustryWorkflowTemplate[];
  templates: IndustryTemplate[];
  compliance: { framework: string; region: string; rules: { key: string; name: string; severity: string }[] }[];
  kpis: IndustryKPI[];
  navigation: Record<string, unknown>;
  selection: { business_type: string | null; company_size: string | null; country: string | null; regulations: string[] } | null;
}

export async function industryCatalog(): Promise<IndustryPackSummary[]> {
  return api<IndustryPackSummary[]>("/industry/catalog");
}

export async function industryCatalogDetail(industryKey: string): Promise<Record<string, unknown>> {
  return api(`/industry/catalog/${industryKey}`);
}

export async function industryMarketplace(): Promise<(IndustryPackSummary & { status: string })[]> {
  return api("/industry/marketplace");
}

export async function industrySelect(payload: Record<string, unknown>): Promise<{ installed: InstalledIndustryPack; selection: IndustrySelection }> {
  return api("/industry/select", { method: "POST", body: payload });
}

export async function industrySelections(): Promise<IndustrySelection[]> {
  return api<IndustrySelection[]>("/industry/selections");
}

export async function industryInstalled(status?: string): Promise<InstalledIndustryPack[]> {
  return api("/industry/installed", { query: { status } });
}

export async function industryInstalledDetail(industryKey: string): Promise<InstalledIndustryPack> {
  return api(`/industry/installed/${industryKey}`);
}

export async function industryInstall(industryKey: string): Promise<InstalledIndustryPack> {
  return api(`/industry/installed/${industryKey}/install`, { method: "POST" });
}

export async function industryUpdate(industryKey: string, payload: Record<string, unknown>): Promise<InstalledIndustryPack> {
  return api(`/industry/installed/${industryKey}`, { method: "PATCH", body: payload });
}

export async function industryUninstall(industryKey: string): Promise<{ industry_key: string; uninstalled: boolean }> {
  return api(`/industry/installed/${industryKey}`, { method: "DELETE" });
}

export async function industryToggleModule(industryKey: string, moduleKey: string, enabled: boolean): Promise<{ modules_enabled: string[] }> {
  return api(`/industry/installed/${industryKey}/modules/${moduleKey}/toggle`, { method: "POST", body: { enabled } });
}

export async function industryTemplates(industryKey: string, kind?: string): Promise<IndustryTemplate[]> {
  return api(`/industry/installed/${industryKey}/templates`, { query: { kind } });
}

export async function industryApplyTemplate(industryKey: string, templateKey: string, context?: Record<string, unknown>): Promise<Record<string, unknown>> {
  return api(`/industry/installed/${industryKey}/templates/${templateKey}/apply`, { method: "POST", body: { context } });
}

export async function industryWorkflowTemplates(industryKey: string): Promise<IndustryWorkflowTemplate[]> {
  return api(`/industry/installed/${industryKey}/workflows/templates`);
}

export async function industryWorkflows(industryKey: string, status?: string): Promise<IndustryWorkflowRun[]> {
  return api(`/industry/installed/${industryKey}/workflows`, { query: { status } });
}

export async function industryWorkflowDetail(industryKey: string, workflowId: string): Promise<IndustryWorkflowRun & { steps: { key: string; name: string; status: string }[]; context: Record<string, unknown> }> {
  return api(`/industry/installed/${industryKey}/workflows/${workflowId}`);
}

export async function industryActivateWorkflow(industryKey: string, templateKey: string, context?: Record<string, unknown>): Promise<Record<string, unknown>> {
  return api(`/industry/installed/${industryKey}/workflows/activate`, { method: "POST", body: { template_key: templateKey, context } });
}

export async function industryAdvanceWorkflow(industryKey: string, workflowId: string, stepKey?: string): Promise<Record<string, unknown>> {
  return api(`/industry/installed/${industryKey}/workflows/${workflowId}/advance`, { method: "POST", body: { step_key: stepKey } });
}

export async function industryWorkflowAction(industryKey: string, workflowId: string, action: "pause" | "resume" | "cancel"): Promise<Record<string, unknown>> {
  return api(`/industry/installed/${industryKey}/workflows/${workflowId}/${action}`, { method: "POST" });
}

export async function industryPolicies(industryKey: string): Promise<IndustryComplianceRule[]> {
  return api(`/industry/installed/${industryKey}/compliance/policies`);
}

export async function industryRunCompliance(industryKey: string, evidence?: Record<string, unknown>, autoStatus?: string): Promise<Record<string, unknown>> {
  return api(`/industry/installed/${industryKey}/compliance/run`, { method: "POST", body: { evidence, auto_status: autoStatus } });
}

export async function industryCompliancePosture(industryKey: string): Promise<IndustryCompliancePosture> {
  return api(`/industry/installed/${industryKey}/compliance/posture`);
}

export async function industryAIProfiles(industryKey: string): Promise<IndustryAIModelProfile[]> {
  return api(`/industry/installed/${industryKey}/ai/profiles`);
}

export async function industryAIToggle(industryKey: string, modelKey: string, enabled: boolean): Promise<{ model_key: string; enabled: boolean }> {
  return api(`/industry/installed/${industryKey}/ai/profiles/${modelKey}/toggle`, { method: "POST", body: { enabled } });
}

export async function industryAIUpdate(industryKey: string, modelKey: string, changes: Record<string, unknown>): Promise<Record<string, unknown>> {
  return api(`/industry/installed/${industryKey}/ai/profiles/${modelKey}`, { method: "PATCH", body: changes });
}

export async function industryAIChat(industryKey: string, question: string, modelKey?: string, skill?: string): Promise<{ content: string; provider: string; model: string; grounded: Record<string, unknown>; profile: string }> {
  return api(`/industry/installed/${industryKey}/ai/chat`, { method: "POST", body: { question, model_key: modelKey, skill } });
}

export async function industryAIStatus(industryKey: string): Promise<{ industry_key: string; profiles: { model_key: string; name: string; enabled: boolean; skills: string[]; guardrails: number }[]; gateway: { provider: string; available: boolean } }> {
  return api(`/industry/installed/${industryKey}/ai/status`);
}

export async function industryKPIs(industryKey: string): Promise<IndustryKPI[]> {
  return api(`/industry/installed/${industryKey}/analytics/kpis`);
}

export async function industryRecordMetrics(industryKey: string, values: { metric_key: string; value: number }[], period?: string): Promise<{ recorded: number; metric_keys: string[] }> {
  return api(`/industry/installed/${industryKey}/analytics/record`, { method: "POST", body: { values, period } });
}

export async function industryAnalytics(industryKey: string, days = 30): Promise<{ industry_key: string; period_days: number; metrics: IndustryMetricCard[]; tracked: number }> {
  return api(`/industry/installed/${industryKey}/analytics/dashboard`, { query: { days } });
}

export async function industryTimeseries(industryKey: string, metricKey?: string, days = 30): Promise<{ id: string; metric_key: string; name: string | null; value: number; unit: string | null; period: string; recorded_at: string | null }[]> {
  return api(`/industry/installed/${industryKey}/analytics/timeseries`, { query: { metric_key: metricKey, days } });
}

export async function industryPackOverview(industryKey: string): Promise<IndustryPackOverview> {
  return api(`/industries/${industryKey}`);
}

export async function industryPackModules(industryKey: string): Promise<IndustryModule[]> {
  return api(`/industries/${industryKey}/modules`);
}

export async function industryPackCompliance(industryKey: string): Promise<{ rules: IndustryComplianceRule[]; posture: IndustryCompliancePosture | null }> {
  return api(`/industries/${industryKey}/compliance`);
}

export async function industryPackAI(industryKey: string): Promise<Record<string, unknown>> {
  return api(`/industries/${industryKey}/ai`);
}

export async function industryPackAnalytics(industryKey: string, days = 30): Promise<Record<string, unknown>> {
  return api(`/industries/${industryKey}/analytics`, { query: { days } });
}

export async function industryPackChat(industryKey: string, question: string): Promise<{ content: string; provider: string }> {
  return api(`/industries/${industryKey}/ai/chat`, { method: "POST", body: { question } });
}

// ============================================================================
// Phase 18 — Autonomous Enterprise Intelligence (Digital Twin)
// ============================================================================

export interface TwinState {
  organization_id: string;
  twin?: Record<string, unknown>;
  entity_counts: Record<string, number>;
  dimensions?: Record<string, unknown>;
  state?: Record<string, unknown>;
  state_history?: TwinSnapshot[];
  predicted_state?: Record<string, unknown>;
  health_score?: number | null;
  health_status?: string | null;
  refresh_count?: number;
  last_refreshed_at?: string | null;
  updated_at?: string | null;
}

export interface TwinSnapshot {
  id?: string;
  captured_at: string | null;
  state: Record<string, unknown>;
  counts?: Record<string, unknown>;
  summary?: Record<string, unknown>;
}

export interface TwinHealth {
  id?: string;
  score: number;
  status: string;
  breakdown: Record<string, { score: number; status: string; detail: string }>;
  period?: string;
  generated_at?: string | null;
}

export interface TwinPrediction {
  id: string;
  kind: string;
  title?: string;
  description?: string;
  probability?: number;
  impact?: string;
  score?: number;
  level: string;
  horizon_days?: number;
  subject_type?: string;
  subject_name?: string;
  signals: string[];
  recommended_action?: string;
  status: string;
  created_at?: string | null;
}

export interface TwinSimulation {
  id: string;
  scenario: string;
  title?: string;
  assumptions?: Record<string, unknown>;
  results: {
    risk?: number;
    cost?: number | string;
    timeline?: string;
    productivity?: string;
    summary?: string;
    feasibility?: number;
    outcomes?: Record<string, unknown> | string[];
  };
  status?: string;
  created_at?: string | null;
}

export interface TwinForecast {
  id: string;
  dimension: string;
  horizon_days: number;
  series: { date: string; value: number }[];
  trend: string;
  summary?: string;
  confidence?: number;
  drivers?: string[];
  generated_at?: string | null;
}

export interface TwinRecommendation {
  id: string;
  kind: string;
  title: string;
  rationale?: string;
  evidence: string[];
  expected_outcome?: string;
  confidence?: number;
  impact?: string;
  status: string;
  created_at?: string | null;
}

export interface TwinOptimization {
  id: string;
  kind: string;
  title: string;
  rationale?: string;
  impact?: string;
  effort?: string;
  expected_gain?: number | string;
  evidence: string[];
  status: string;
  applied_at?: string | null;
  created_at?: string | null;
}

export interface TwinDecision {
  id: string;
  decided_by?: string;
  category: string;
  decision: string;
  reason?: string;
  alternatives: string[];
  evidence: Record<string, unknown>[];
  outcome?: string;
  outcome_score?: number;
  lessons: string[];
  status: string;
  analyzed: boolean;
  decided_at?: string | null;
  created_at?: string | null;
}

export interface TwinIntelligenceCenter {
  twin: TwinState | null;
  health: TwinHealth | null;
  predictions: TwinPrediction[];
  recommendations: TwinRecommendation[];
  simulations: TwinSimulation[];
  forecasts: TwinForecast[];
  optimizations: TwinOptimization[];
  decisions: TwinDecision[];
  generated_at: string;
}

export interface TwinBrief {
  organization_id: string;
  generated_at: string;
  summary: string;
  highlights: Record<string, number | string | null>;
}

export interface TwinAnswer {
  question: string;
  intent: string;
  answer: string;
  context: Record<string, unknown>;
}

export async function getTwin(refresh = false): Promise<TwinState> {
  return api<TwinState>("/twin", { query: { refresh } });
}

export async function refreshTwin(): Promise<{ status: string; organization_id: string }> {
  return api("/twin/refresh", { method: "POST" });
}

export async function getTwinHistory(limit = 30): Promise<{ total: number; history: TwinSnapshot[] }> {
  return api("/twin/history", { query: { limit } });
}

export async function getTwinHealth(): Promise<TwinHealth> {
  return api<TwinHealth>("/twin/health");
}

export async function getTwinHealthHistory(limit = 30): Promise<{ total: number; history: TwinHealth[] }> {
  return api("/twin/health/history", { query: { limit } });
}

export async function generatePredictions(): Promise<{ total: number; predictions: TwinPrediction[] }> {
  return api("/twin/predictions/generate", { method: "POST" });
}

export async function listPredictions(status?: string): Promise<{ total: number; predictions: TwinPrediction[] }> {
  return api("/twin/predictions", { query: { status } });
}

export async function acknowledgePrediction(id: string): Promise<TwinPrediction> {
  return api(`/twin/predictions/${id}/acknowledge`, { method: "POST" });
}

export async function dismissPrediction(id: string): Promise<TwinPrediction> {
  return api(`/twin/predictions/${id}/dismiss`, { method: "POST" });
}

export async function runTwinSimulation(scenario: string, params?: Record<string, unknown>): Promise<TwinSimulation> {
  return api("/twin/simulations/run", { method: "POST", body: { scenario, params: params ?? {} } });
}

export async function listTwinSimulations(): Promise<{ total: number; simulations: TwinSimulation[] }> {
  return api("/twin/simulations");
}

export async function getTwinSimulation(id: string): Promise<TwinSimulation> {
  return api(`/twin/simulations/${id}`);
}

export async function generateTwinForecasts(): Promise<{ total: number; forecasts: TwinForecast[] }> {
  return api("/twin/forecasts/generate", { method: "POST" });
}

export async function listTwinForecasts(): Promise<{ total: number; forecasts: TwinForecast[] }> {
  return api("/twin/forecasts");
}

export async function generateRecommendations(): Promise<{ total: number; recommendations: TwinRecommendation[] }> {
  return api("/twin/recommendations/generate", { method: "POST" });
}

export async function listTwinRecommendations(status?: string): Promise<{ total: number; recommendations: TwinRecommendation[] }> {
  return api("/twin/recommendations", { query: { status } });
}

export async function setTwinRecommendationStatus(id: string, status: "accepted" | "dismissed"): Promise<TwinRecommendation> {
  return api(`/twin/recommendations/${id}/status`, { method: "POST", body: { status } });
}

export async function generateOptimizations(): Promise<{ total: number; optimizations: TwinOptimization[] }> {
  return api("/twin/optimization/generate", { method: "POST" });
}

export async function listOptimizations(): Promise<{ total: number; optimizations: TwinOptimization[] }> {
  return api("/twin/optimization");
}

export async function applyOptimization(id: string): Promise<TwinOptimization> {
  return api(`/twin/optimization/${id}/apply`, { method: "POST" });
}

export async function createTwinDecision(payload: {
  decision: string;
  category?: string;
  reason?: string;
  alternatives?: string[];
  evidence?: Record<string, unknown>[];
}): Promise<TwinDecision> {
  return api("/twin/decisions", { method: "POST", body: payload });
}

export async function recordDecisionOutcome(id: string, outcome: string, outcome_score: number): Promise<TwinDecision> {
  return api(`/twin/decisions/${id}/outcome`, { method: "POST", body: { outcome, outcome_score } });
}

export async function analyzeDecision(id: string): Promise<TwinDecision> {
  return api(`/twin/decisions/${id}/analyze`, { method: "POST" });
}

export async function listTwinDecisions(): Promise<{ total: number; decisions: TwinDecision[] }> {
  return api("/twin/decisions");
}

export async function getTwinIntelligence(): Promise<TwinIntelligenceCenter> {
  return api<TwinIntelligenceCenter>("/twin/intelligence");
}

export async function getTwinBrief(): Promise<TwinBrief> {
  return api<TwinBrief>("/twin/brief");
}

export async function askTwin(question: string): Promise<TwinAnswer> {
  return api<TwinAnswer>("/twin/ask", { method: "POST", body: { question } });
}

// ============================================================================
// Phase 18 — Developer Ecosystem
// ============================================================================

export interface DeveloperProfile {
  id: string;
  developer_key: string;
  name: string;
  email: string;
  bio?: string;
  website?: string;
  country?: string;
  status: string;
  verified: boolean;
  verified_at?: string | null;
  created_at?: string;
}

export interface DeveloperSubscription {
  id: string;
  developer_id: string;
  plan: string;
  revenue_share: number;
  status: string;
  monthly_quota?: number | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
}

export interface DeveloperApplication {
  id: string;
  application_key: string;
  name: string;
  app_type: string;
  description?: string;
  version: string;
  status: string;
  scopes?: string[];
  endpoints?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  verified: boolean;
  published_at?: string | null;
  created_at?: string;
}

export interface DeveloperApiKey {
  id: string;
  application_id: string;
  name: string;
  key_prefix: string;
  api_key?: string;
  scopes?: string[];
  rate_limit_per_minute: number;
  status: string;
  expires_at?: string | null;
  last_used_at?: string | null;
  created_at?: string;
}

export interface DeveloperUsageSummary {
  developer_id: string;
  days: number;
  period_end: string;
  totals: { requests: number; errors: number; latency_ms: number; installs: number };
  by_day: Record<string, Record<string, number>>;
}

export interface DeveloperCertification {
  id: string;
  developer_id: string;
  exam: string;
  status: string;
  score: number;
  badge: string;
  issued_at?: string;
  expires_at?: string | null;
}

export interface AIAgent {
  id: string;
  organization_id?: string | null;
  developer_id?: string | null;
  agent_key: string;
  name: string;
  description?: string;
  role: string;
  capabilities?: string[];
  permissions?: string[];
  knowledge_scopes?: string[];
  status: string;
  config?: Record<string, unknown>;
  version: string;
  verified: boolean;
  installed_at?: string | null;
  created_at?: string;
}

export interface WebhookEndpoint {
  id: string;
  organization_id: string;
  name: string;
  url: string;
  events?: string[];
  status: string;
  success_count: number;
  failure_count: number;
  last_delivered_at?: string | null;
  created_at?: string;
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event_name: string;
  attempts: number;
  status: string;
  response_code?: number | null;
  response_body?: string | null;
  error?: string | null;
  delivered_at?: string | null;
  created_at?: string;
}

export interface MarketplaceListing {
  id: string;
  plugin_key: string;
  name: string;
  description?: string;
  category: string;
  price: number;
  rating: number;
  review_count: number;
  downloads: number;
  version: string;
  verified: boolean;
  scanned: boolean;
  published: boolean;
  manifest?: Record<string, unknown>;
}

export interface ExtensionInstall {
  id: string;
  marketplace_item_id: string;
  organization_id: string;
  status: string;
  settings?: Record<string, unknown>;
  installed_by?: string | null;
  installed_at?: string | null;
}

export interface MarketplaceReview {
  id: string;
  item_id: string;
  user_id: string;
  rating: number;
  comment?: string;
  created_at?: string;
}

export interface Theme {
  id: string;
  organization_id: string;
  name: string;
  config: Record<string, unknown>;
  active: boolean;
  source: string;
  created_at?: string;
}

export async function registerDeveloper(payload: {
  name: string;
  email: string;
  bio?: string;
  website?: string;
  country?: string;
}): Promise<DeveloperProfile> {
  return api("/developers/register", { method: "POST", body: payload });
}

export async function getDeveloperMe(): Promise<{ profile: DeveloperProfile; subscription: DeveloperSubscription }> {
  return api("/developers/me");
}

export async function listDevelopers(limit = 100): Promise<{ total: number; developers: DeveloperProfile[] }> {
  return api("/developers", { query: { limit } });
}

export async function verifyDeveloper(id: string, verified = true): Promise<DeveloperProfile> {
  return api(`/developers/${id}/verify`, { method: "POST", query: { verified } });
}

export async function listMyApplications(): Promise<{ total: number; applications: DeveloperApplication[] }> {
  return api("/developers/me/applications");
}

export async function createApplication(payload: {
  name: string;
  app_type: string;
  description?: string;
  scopes?: string[];
}): Promise<DeveloperApplication> {
  return api("/developers/me/applications", { method: "POST", body: payload });
}

export async function updateApplication(id: string, payload: Record<string, unknown>): Promise<DeveloperApplication> {
  return api(`/developers/me/applications/${id}`, { method: "PATCH", body: payload });
}

export async function publishApplication(id: string): Promise<DeveloperApplication> {
  return api(`/developers/me/applications/${id}/publish`, { method: "POST" });
}

export async function delistApplication(id: string): Promise<DeveloperApplication> {
  return api(`/developers/me/applications/${id}/delist`, { method: "POST" });
}

export async function createDeveloperApiKey(applicationId: string, payload: {
  name: string;
  scopes?: string[];
  rate_limit_per_minute?: number;
}): Promise<DeveloperApiKey> {
  return api(`/developers/me/applications/${applicationId}/keys`, { method: "POST", body: payload });
}

export async function listDeveloperApiKeys(applicationId: string): Promise<{ total: number; keys: DeveloperApiKey[] }> {
  return api(`/developers/me/applications/${applicationId}/keys`);
}

export async function revokeDeveloperApiKey(keyId: string): Promise<DeveloperApiKey> {
  return api(`/developers/me/keys/${keyId}/revoke`, { method: "POST" });
}

export async function getDeveloperAnalytics(days = 30): Promise<DeveloperUsageSummary> {
  return api(`/developers/me/analytics`, { query: { days } });
}

export async function recordUsage(payload: {
  application_id: string;
  usage_date: string;
  unit: string;
  value: number;
}): Promise<Record<string, unknown>> {
  return api("/developers/usage/record", { method: "POST", body: payload });
}

export async function getDeveloperSubscription(): Promise<DeveloperSubscription> {
  return api("/developers/me/subscription");
}

export async function changeDeveloperPlan(plan: string): Promise<DeveloperSubscription> {
  return api("/developers/me/subscription/plan", { method: "POST", body: { plan } });
}

export async function attemptCertification(exam: string, score: number): Promise<DeveloperCertification> {
  return api("/developers/me/certifications/attempt", { method: "POST", body: { exam, score } });
}

export async function listMyCertifications(): Promise<{ total: number; certifications: DeveloperCertification[] }> {
  return api("/developers/me/certifications");
}

export async function createAgent(payload: {
  name: string;
  description?: string;
  role?: string;
  capabilities?: string[];
  permissions?: string[];
  knowledge_scopes?: string[];
}): Promise<AIAgent> {
  return api("/agents", { method: "POST", body: payload });
}

export async function listAgents(status?: string): Promise<{ total: number; agents: AIAgent[] }> {
  return api("/agents", { query: { status } });
}

export async function getAgent(id: string): Promise<AIAgent> {
  return api(`/agents/${id}`);
}

export async function setAgentStatus(id: string, status: string): Promise<AIAgent> {
  return api(`/agents/${id}/status`, { method: "PATCH", body: { status } });
}

export async function executeAgent(id: string, inputText: string): Promise<Record<string, unknown>> {
  return api(`/agents/${id}/execute`, { method: "POST", body: { input_text: inputText } });
}

export async function createWebhook(payload: {
  name: string;
  url: string;
  events?: string[];
  secret?: string;
}): Promise<WebhookEndpoint> {
  return api("/webhooks", { method: "POST", body: payload });
}

export async function listWebhooks(): Promise<{ total: number; endpoints: WebhookEndpoint[] }> {
  return api("/webhooks");
}

export async function setWebhookStatus(id: string, status: "active" | "paused" | "failing"): Promise<WebhookEndpoint> {
  return api(`/webhooks/${id}/status`, { method: "PATCH", body: { status } });
}

export async function deleteWebhook(id: string): Promise<{ status: string; endpoint_id: string }> {
  return api(`/webhooks/${id}`, { method: "DELETE" });
}

export async function listWebhookDeliveries(endpointId?: string): Promise<{ total: number; deliveries: WebhookDelivery[] }> {
  return api("/webhooks/deliveries", { query: { endpoint_id: endpointId } });
}

export async function redeliverWebhook(deliveryId: string): Promise<WebhookDelivery> {
  return api(`/webhooks/deliveries/${deliveryId}/redeliver`, { method: "POST" });
}

export async function testWebhook(id: string, payload?: Record<string, unknown>): Promise<{ event: string; signature: string | null; delivered: boolean }> {
  return api(`/webhooks/${id}/test`, { method: "POST", body: payload ?? {} });
}

export async function publishListing(payload: {
  application_id: string;
  name: string;
  description?: string;
  category?: string;
  price?: number;
}): Promise<MarketplaceListing> {
  return api("/marketplace/listings", { method: "POST", body: payload });
}

export async function listListings(category?: string): Promise<{ total: number; listings: MarketplaceListing[] }> {
  return api("/marketplace/listings", { query: { category } });
}

export async function getListing(id: string): Promise<MarketplaceListing> {
  return api(`/marketplace/listings/${id}`);
}

export async function verifyListing(id: string, verified = true): Promise<MarketplaceListing> {
  return api(`/marketplace/listings/${id}/verify`, { method: "POST", query: { verified } });
}

export async function installExtension(itemId: string, asAgent = false): Promise<ExtensionInstall> {
  return api("/marketplace/install", { method: "POST", body: { item_id: itemId, as_agent: asAgent } });
}

export async function listInstalledExtensions(): Promise<{ total: number; installed: ExtensionInstall[] }> {
  return api("/marketplace/installed");
}

export async function uninstallExtension(itemId: string): Promise<ExtensionInstall> {
  return api("/marketplace/uninstall", { method: "POST", body: { item_id: itemId } });
}

export async function addListingReview(itemId: string, rating: number, comment?: string): Promise<MarketplaceReview> {
  return api("/marketplace/reviews", { method: "POST", body: { item_id: itemId, rating, comment } });
}

export async function listingReviews(itemId: string): Promise<{ total: number; reviews: MarketplaceReview[] }> {
  return api(`/marketplace/listings/${itemId}/reviews`);
}

export async function listThemes(): Promise<{ total: number; themes: Theme[] }> {
  return api("/themes");
}

export async function createTheme(payload: {
  name: string;
  config?: Record<string, unknown>;
  source?: string;
  activate?: boolean;
}): Promise<Theme> {
  return api("/themes", { method: "POST", body: payload });
}

export async function updateTheme(id: string, payload: Record<string, unknown>): Promise<Theme> {
  return api(`/themes/${id}`, { method: "PATCH", body: payload });
}

export async function activateTheme(id: string): Promise<Theme> {
  return api(`/themes/${id}/activate`, { method: "POST" });
}

export async function deleteTheme(id: string): Promise<{ status: string; theme_id: string }> {
  return api(`/themes/${id}`, { method: "DELETE" });
}


// ------------------------------------------------------- Slice 4D.1 brain

export async function brainAnswer(payload: BrainAnswerRequest): Promise<BrainAnswer> {
  return api<BrainAnswer>("/brain/answer", { method: "POST", body: payload });
}

export async function brainKnowledgeSearch(
  payload: BrainKnowledgeSearchRequest
): Promise<BrainKnowledgeSearchResponse> {
  return api<BrainKnowledgeSearchResponse>("/brain/knowledge/search", {
    method: "POST",
    body: payload,
  });
}


// ------------------------------------------------------- Slice 4D.3 memory

export async function brainMemoryFeed(params?: {
  memory_category?: string;
  status?: string;
  limit?: number;
}): Promise<BrainMemoryFeedResponse> {
  return api<BrainMemoryFeedResponse>("/brain/memory/feed", { query: params });
}

export async function brainMemorySearch(payload: {
  question: string;
  limit?: number;
}): Promise<BrainMemorySearchResponse> {
  return api<BrainMemorySearchResponse>("/brain/memory/search", {
    method: "POST",
    body: payload,
  });
}

export async function brainMemoryTimeline(params?: {
  limit?: number;
}): Promise<BrainMemoryTimelineResponse> {
  return api<BrainMemoryTimelineResponse>("/brain/memory/timeline", { query: params });
}

export async function brainMemoryGet(memoryId: string): Promise<BrainMemory> {
  return api<BrainMemory>(`/brain/memory/${memoryId}`);
}

export async function brainMemoryEvidence(memoryId: string): Promise<BrainMemoryEvidenceResponse> {
  return api<BrainMemoryEvidenceResponse>(`/brain/memory/${memoryId}/evidence`);
}

export async function brainMemoryRelated(memoryId: string): Promise<BrainMemoryRelatedResponse> {
  return api<BrainMemoryRelatedResponse>(`/brain/memory/${memoryId}/related`);
}

export async function brainMemoryRecordOutcome(
  memoryId: string,
  payload: BrainMemoryOutcomeRequest
): Promise<BrainMemory> {
  return api<BrainMemory>(`/brain/memory/${memoryId}/outcome`, {
    method: "POST",
    body: payload,
  });
}


// ------------------------------------------------------- Slice 4D.4 patterns

export async function brainPatternsList(params?: {
  pattern_type?: string;
  status?: string;
  limit?: number;
}): Promise<BrainPatternsListResponse> {
  return api<BrainPatternsListResponse>("/brain/patterns", { query: params });
}

export async function brainPatternGet(patternId: string): Promise<BrainPattern> {
  return api<BrainPattern>(`/brain/patterns/${patternId}`);
}

export async function brainPatternEvidence(
  patternId: string
): Promise<BrainPatternEvidenceResponse> {
  return api<BrainPatternEvidenceResponse>(`/brain/patterns/${patternId}/evidence`);
}

export async function brainPatternHistory(
  patternId: string,
  params?: { limit?: number }
): Promise<BrainPatternHistoryResponse> {
  return api<BrainPatternHistoryResponse>(`/brain/patterns/${patternId}/history`, {
    query: params,
  });
}

export async function brainPatternRelated(
  patternId: string,
  params?: { limit?: number }
): Promise<BrainPatternRelatedResponse> {
  return api<BrainPatternRelatedResponse>(`/brain/patterns/${patternId}/related`, {
    query: params,
  });
}

export async function brainPatternSetStatus(
    patternId: string,
    status: string
  ): Promise<{ id: string; status: string }> {
    return api(`/brain/patterns/${patternId}`, {
      method: "PATCH",
      body: { status },
    });
  }

  export async function brainInsightsList(params?: {
    status?: string;
    insight_type?: string;
    severity?: string;
    limit?: number;
  }): Promise<BrainInsightsListResponse> {
    return api<BrainInsightsListResponse>("/brain/insights", { query: params });
  }

  export async function brainInsightGet(insightId: string): Promise<BrainInsight> {
    return api<BrainInsight>(`/brain/insights/${insightId}`);
  }

  export async function brainInsightEvidence(
    insightId: string
  ): Promise<BrainInsightEvidenceResponse> {
    return api<BrainInsightEvidenceResponse>(`/brain/insights/${insightId}/evidence`);
  }

  export async function brainInsightHistory(
    insightId: string,
    params?: { limit?: number }
  ): Promise<BrainInsightHistoryResponse> {
    return api<BrainInsightHistoryResponse>(`/brain/insights/${insightId}/history`, {
      query: params,
    });
  }

  export async function brainInsightRelated(
    insightId: string,
    params?: { limit?: number }
  ): Promise<BrainInsightRelatedResponse> {
    return api<BrainInsightRelatedResponse>(`/brain/insights/${insightId}/related`, {
      query: params,
    });
  }

export async function brainGraphRelationshipSync(payload: {
  entity_type?: string;
  entity_id?: string;
}): Promise<{ synced: number; mode: "entity" | "recent" }> {
  return api("/brain/graph/relationships/sync", { method: "POST", body: payload });
}

export async function brainGraphRelationshipTraverse(
  nodeType: string,
  nodeId: string,
  maxDepth = 3
): Promise<BrainGraphTraversal> {
  return api<BrainGraphTraversal>("/brain/graph/relationships/traverse", {
    query: { node_type: nodeType, node_id: nodeId, max_depth: maxDepth },
  });
}
