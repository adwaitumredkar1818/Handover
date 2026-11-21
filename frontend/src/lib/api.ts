import type {
  User,
  AuthSessionResponse,
  Organisation,
  OrganisationMember,
  Project,
  ProjectOverview,
  ProjectMember,
  ProjectTransition,
  ProjectActivityCard,
  SourceConnection,
  ProjectSourceMapping,
  EvidenceSummary,
  EvidenceDetail,
  EvidenceMetrics,
  AssistantConversation,
  AssistantConversationDetail,
  AssistantAnswerResponse,
  AssistantResponseMode,
  InvitationSummary,
  CreateInvitationResponse,
  InvitationListResponse,
  InvitationPreviewResponse,
  AcceptInvitationResponse,
  RegisterWithInvitationResponse,
  ProjectProcessingStatus,
  VerifyEmailResponse,
  RequestEmailVerificationResponse,
  HandoverPackageVersionSummary,
  HandoverVersionSectionsResponse,
  HandoverContextContributionResponse,
  HandoverReadinessIntelligenceResponse,
  HandoverChecklistGroupDetail,
  HandoverChecklistItemDetail,
  HandoverChecklistWorkspaceResponse,
  HandoverResponsibilityTransferDetail,
  HandoverResponsibilityWorkspaceResponse,
  HandoverSignoffRecord,
  HandoverSignoffWorkspaceResponse,
  HandoverDeliveryRecord,
  HandoverAcknowledgementRecord,
} from "./types";
import type {
  VerificationSummaryResponse,
  VerificationQueueResponse,
  VerificationCaseDetail,
  CaseEvidenceResponse,
  HandoverEligibilityResponse,
  VerificationContextRequest,
  ConflictSummaryResponse,
  ConflictListResponse,
  VerificationConflictItem,
  DetectConflictsResponse,
  QueueFilterParams,
  ChangeImpactFeedResponse,
} from "../types/verification";

export interface OnboardingStepProgressItem {
  step_id: string;
  is_completed: boolean;
  completed_at?: string | null;
}

export interface OnboardingProgressResponse {
  project_id: string;
  user_id: string;
  completed_steps: Record<string, boolean>;
  items: OnboardingStepProgressItem[];
}

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured) {
    const trimmed = configured.replace(/\/$/, "");
    if (typeof window !== "undefined") {
      try {
        const parsed = new URL(trimmed);
        if (
          (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") &&
          window.location.hostname !== "localhost" &&
          window.location.hostname !== "127.0.0.1"
        ) {
          parsed.hostname = window.location.hostname;
          return parsed.toString().replace(/\/$/, "");
        }
      } catch {}
    }
    return trimmed;
  }
  if (typeof window !== "undefined") {
    // In browser without configured base url, fall back to same-origin relative URL
    return "/api/v1";
  }
  return "http://127.0.0.1:8000/api/v1";
}

const API_BASE_URL = getApiBaseUrl();

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("handover_access_token");
}

export function setStoredToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("handover_access_token", token);
  } else {
    localStorage.removeItem("handover_access_token");
  }
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("handover_cached_user");
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: User | null) {
  if (typeof window === "undefined") return;
  if (user) {
    localStorage.setItem("handover_cached_user", JSON.stringify(user));
  } else {
    localStorage.removeItem("handover_cached_user");
  }
}

let refreshSessionPromise: Promise<AuthSessionResponse | null> | null = null;

async function refreshSessionSingleFlight(): Promise<AuthSessionResponse | null> {
  if (typeof window === "undefined") return null;
  if (!refreshSessionPromise) {
    refreshSessionPromise = (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
        });
        if (!res.ok) {
          setStoredToken(null);
          setStoredUser(null);
          return null;
        }
        const data = (await res.json()) as AuthSessionResponse;
        if (data?.access_token) {
          setStoredToken(data.access_token);
          if (data.user) setStoredUser(data.user);
          return data;
        }
        setStoredToken(null);
        setStoredUser(null);
        return null;
      } catch {
        setStoredToken(null);
        setStoredUser(null);
        return null;
      } finally {
        refreshSessionPromise = null;
      }
    })();
  }
  return refreshSessionPromise;
}

async function tryRefreshToken(): Promise<string | null> {
  const data = await refreshSessionSingleFlight();
  return data?.access_token ?? null;
}

interface ApiErrorPayload {
  error?: {
    message?: string;
    details?: unknown;
  };
  message?: string;
  detail?: unknown;
  details?: unknown;
}

interface ValidationDetailItem {
  msg?: string;
  loc?: unknown[];
}

interface RawOverviewResponse {
  readiness?: ProjectOverview["readiness"];
  sources?: ProjectOverview["sources"];
  project_summary?: {
    project_id?: string;
    name?: string;
    status?: string;
    target_completion_date?: string | null;
    owner?: { id: string; full_name: string; email: string };
    departing_member?: { id: string; full_name: string; email: string } | null;
    successor?: { id: string; full_name: string; email: string } | null;
  };
  connected_sources?: {
    total_sources?: number;
    active_providers?: string[];
    health_status?: string;
  };
  evidence_overview?: {
    total_records?: number;
    document_count?: number;
    by_provider?: Record<string, number>;
  };
  knowledge_overview?: {
    decisions_count?: number;
    tasks_count?: number;
    risks_count?: number;
    responsibilities_count?: number;
    dependencies_count?: number;
    availability?: string;
  };
  attention_required?: Array<{
    id?: string;
    type?: string;
    message?: string;
    resource_id?: string | null;
  }>;
  attention_items?: Array<{
    id?: string;
    type?: string;
    message?: string;
    resource_id?: string | null;
  }>;
  recent_activity?: Array<{
    id?: string;
    event_type?: string;
    description?: string;
    actor_name?: string | null;
    timestamp?: string;
  }>;
}

const inFlightRequests = new Map<string, Promise<unknown>>();
const getCache = new Map<string, { timestamp: number; data: unknown }>();
const CACHE_TTL_MS = 2000; // 2s in-memory deduplication for concurrent callers without freezing live sync

export function clearApiCache(pathPrefix?: string) {
  if (!pathPrefix) {
    getCache.clear();
    return;
  }
  for (const key of Array.from(getCache.keys())) {
    if (key.includes(pathPrefix)) {
      getCache.delete(key);
    }
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  isRetry = false
): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const token = getToken();

  // If modifying data, invalidate cached GET endpoints for this project/resource
  if (method !== 'GET') {
    const segments = path.split('/').filter(Boolean);
    const scopePrefix = segments.length >= 2 ? `/${segments[0]}/${segments[1]}` : '';
    if (scopePrefix) clearApiCache(scopePrefix);
    else getCache.clear();
  } else if (!isRetry && !options.body) {
    const cacheKey = `${path}:${token || ''}`;
    const cached = getCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data as T;
    }
    const pending = inFlightRequests.get(cacheKey);
    if (pending) {
      return pending as Promise<T>;
    }
    const promise = (async () => {
      try {
        const result = await requestInternal<T>(path, options, isRetry);
        getCache.set(cacheKey, { timestamp: Date.now(), data: result });
        return result;
      } finally {
        inFlightRequests.delete(cacheKey);
      }
    })();
    inFlightRequests.set(cacheKey, promise);
    return promise;
  }

  return requestInternal<T>(path, options, isRetry);
}

async function requestInternal<T>(
  path: string,
  options: RequestInit = {},
  isRetry = false
): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`;
  const token = getToken();

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    ...options,
    credentials: options.credentials || "include",
    headers,
  });

  if (
    res.status === 401 &&
    !isRetry &&
    !path.startsWith("/auth/login") &&
    !path.startsWith("/auth/refresh") &&
    !path.startsWith("/auth/register")
  ) {
    const newToken = await tryRefreshToken();
    if (newToken) {
      return request<T>(
        path,
        {
          ...options,
          headers: {
            ...headers,
            Authorization: `Bearer ${newToken}`,
          },
        },
        true
      );
    } else {
      setStoredToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("handover:session-expired"));
      }
    }
  }

  if (!res.ok) {
    let errorData: ApiErrorPayload | null = null;
    try {
      errorData = (await res.json()) as ApiErrorPayload;
    } catch {
      // ignore
    }
    let message =
      errorData?.error?.message ||
      errorData?.message ||
      `HTTP error ${res.status}: ${res.statusText}`;

    const details = errorData?.error?.details || errorData?.detail || errorData?.details;
    if (details) {
      if (typeof details === "string") {
        message = details;
      } else if (Array.isArray(details)) {
        const detailMsgs = details.map((d: unknown) => {
          if (typeof d === "string") return d;
          const item = d as ValidationDetailItem | null;
          if (item?.msg) {
            const loc = Array.isArray(item.loc) ? item.loc.slice(-1)[0] : "";
            const cleanMsg = String(item.msg).replace(/^Value error,\s*/i, "");
            return loc && loc !== "body" ? `${String(loc)}: ${cleanMsg}` : cleanMsg;
          }
          return JSON.stringify(d);
        });
        message = detailMsgs.filter(Boolean).join(". ");
      }
    }
    throw new ApiError(message, res.status, errorData);
  }

  if (res.status === 204) {
    return {} as T;
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json() as Promise<T>;
  }
  if (contentType.includes("text/")) {
    return res.text() as unknown as Promise<T>;
  }
  if (contentType.includes("application/pdf") || contentType.includes("octet-stream")) {
    return res.blob() as unknown as Promise<T>;
  }

  return res.json() as Promise<T>;
}

function unwrapList<T>(res: unknown): T[] {
  if (!res) return [];
  if (Array.isArray(res)) return res as T[];
  if (typeof res === "object" && "items" in res) {
    const items = (res as { items?: unknown }).items;
    if (Array.isArray(items)) return items as T[];
  }
  return [];
}

export const api = {
  // Authentication
  auth: {
    async register(data: { email: string; password: string; full_name: string }): Promise<User> {
      return request<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async registerWithInvitation(data: {
      invitation_token: string;
      full_name: string;
      password: string;
      email?: string;
    }): Promise<RegisterWithInvitationResponse> {
      return request<RegisterWithInvitationResponse>("/auth/register-with-invitation", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async verifyEmail(token: string): Promise<VerifyEmailResponse> {
      return request<VerifyEmailResponse>("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
    },
    async resendVerification(email?: string): Promise<RequestEmailVerificationResponse> {
      return request<RequestEmailVerificationResponse>("/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify(email ? { email } : {}),
      });
    },
    async login(data: { email: string; password: string }): Promise<AuthSessionResponse> {
      return request<AuthSessionResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async exchangeSupabaseToken(accessToken: string): Promise<AuthSessionResponse> {
      return request<AuthSessionResponse>("/auth/supabase/exchange", {
        method: "POST",
        body: JSON.stringify({ access_token: accessToken }),
      });
    },
    async refreshToken(): Promise<AuthSessionResponse> {
      const data = await refreshSessionSingleFlight();
      if (!data?.access_token) {
        throw new ApiError("Session expired. Please sign in again.", 401);
      }
      return data;
    },
    async logout(): Promise<void> {
      try {
        await request("/auth/logout", { method: "POST" });
      } catch {
        // ignore network error on logout
      } finally {
        setStoredToken(null);
        setStoredUser(null);
      }
    },
    async me(): Promise<User> {
      return request<User>("/auth/me");
    },
    async forgotPassword(data: { email: string }): Promise<{ message: string; reset_token?: string | null }> {
      return request<{ message: string; reset_token?: string | null }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async resetPassword(data: { token: string; new_password: string }): Promise<{ message: string }> {
      return request<{ message: string }>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  },

  // Organisations
  organisations: {
    async list(): Promise<Organisation[]> {
      const res = await request<unknown>("/organisations");
      return unwrapList<Organisation>(res);
    },
    async create(data: { name: string; slug?: string; description?: string }): Promise<Organisation> {
      return request<Organisation>("/organisations", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async get(orgId: string): Promise<Organisation> {
      return request<Organisation>(`/organisations/${orgId}`);
    },
    async listMembers(orgId: string): Promise<OrganisationMember[]> {
      const res = await request<unknown>(`/organisations/${orgId}/members`);
      return unwrapList<OrganisationMember>(res);
    },
    async updateMemberName(orgId: string, userId: string, fullName: string): Promise<OrganisationMember> {
      return request<OrganisationMember>(`/organisations/${orgId}/members/${userId}/name`, {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName }),
      });
    },
    async listInvitations(
      orgId: string,
      params?: { status?: string; limit?: number; offset?: number }
    ): Promise<InvitationListResponse> {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.limit) qs.set("limit", String(params.limit));
      if (params?.offset) qs.set("offset", String(params.offset));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request<InvitationListResponse>(`/organisations/${orgId}/invitations${suffix}`);
    },
    async createInvitation(
      orgId: string,
      data: { email: string; role_name: string; expires_in_hours?: number }
    ): Promise<CreateInvitationResponse> {
      return request<CreateInvitationResponse>(`/organisations/${orgId}/invitations`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async revokeInvitation(orgId: string, invitationId: string): Promise<InvitationSummary> {
      return request<InvitationSummary>(
        `/organisations/${orgId}/invitations/${invitationId}`,
        { method: "DELETE" }
      );
    },
  },

  // Invitations
  invitations: {
    async preview(token: string): Promise<InvitationPreviewResponse> {
      return request<InvitationPreviewResponse>(`/invitations/${encodeURIComponent(token)}`);
    },
    async accept(token: string): Promise<AcceptInvitationResponse> {
      return request<AcceptInvitationResponse>(`/invitations/${encodeURIComponent(token)}/accept`, {
        method: "POST",
      });
    },
  },

  // Projects
  projects: {
    async list(orgId: string): Promise<Project[]> {
      const res = await request<unknown>(`/organisations/${orgId}/projects`);
      return unwrapList<Project>(res);
    },
    async create(orgId: string, data: { name: string; slug?: string; description?: string; target_handover_date?: string }): Promise<Project> {
      return request<Project>(`/organisations/${orgId}/projects`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async get(projectId: string): Promise<Project> {
      return request<Project>(`/projects/${projectId}`);
    },
    async getOverview(projectId: string): Promise<ProjectOverview> {
      const raw = await request<RawOverviewResponse>(`/projects/${projectId}/overview`);
      if (raw && raw.readiness && raw.sources) {
        return raw as unknown as ProjectOverview;
      }
      const summary = raw?.project_summary || {};
      const connSources = raw?.connected_sources || {};
      const evidOverview = raw?.evidence_overview || {};
      const knowOverview = raw?.knowledge_overview || {};
      const attention = raw?.attention_required || raw?.attention_items || [];
      const activity = raw?.recent_activity || [];

      const totalEvid = evidOverview.total_records || 0;
      const totalSources = connSources.total_sources || 0;
      let readinessPct = 10;
      if (totalSources > 0) readinessPct += 20;
      if (totalEvid > 0) readinessPct += 30;
      if ((knowOverview.decisions_count || 0) > 0 || (knowOverview.tasks_count || 0) > 0) {
        readinessPct += 40;
      }
      readinessPct = Math.min(readinessPct, 100);

      const targetDate = summary.target_completion_date || null;
      let daysRemaining: number | null = null;
      if (targetDate) {
        const diffMs = new Date(targetDate).getTime() - Date.now();
        daysRemaining = Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
      }

      return {
        project_id: summary.project_id || projectId,
        project_name: summary.name || "",
        status: summary.status || "active",
        target_handover_date: targetDate,
        readiness: {
          overall_readiness_pct: readinessPct,
          status: readinessPct >= 80 ? "Ready for Review" : readinessPct >= 40 ? "Reconstruction Active" : "In Preparation",
          target_date: targetDate,
          days_remaining: daysRemaining,
        },
        sources: {
          connected_count: totalSources,
          active_count: (connSources.active_providers || []).length,
          failed_count: connSources.health_status === "error" || connSources.health_status === "failed" ? 1 : 0,
          total_resources: totalSources,
        },
        evidence: {
          total_evidence_items: totalEvid,
          indexed_chunks_count: evidOverview.document_count || totalEvid,
          last_ingested_at: null,
          providers_breakdown: evidOverview.by_provider || {},
        },
        knowledge: {
          decisions_count: knowOverview.decisions_count || 0,
          tasks_count: knowOverview.tasks_count || 0,
          risks_count: knowOverview.risks_count || 0,
          responsibilities_count: knowOverview.responsibilities_count || 0,
          dependencies_count: knowOverview.dependencies_count || 0,
          availability: knowOverview.availability || "available",
        },
        attention_items: attention.map((a) => ({
          id: a.id || String(Math.random()),
          type: a.type || "notice",
          message: a.message || "",
          resource_id: a.resource_id || null,
        })),
        recent_activity: activity.map((ac) => ({
          id: ac.id || String(Math.random()),
          event_type: ac.event_type || "activity",
          description: ac.description || "",
          actor_name: ac.actor_name || null,
          timestamp: ac.timestamp || new Date().toISOString(),
        })),
        departing_member: summary.departing_member || null,
        successor: summary.successor || null,
        owner: summary.owner || null,
      };
    },
    async getTransition(projectId: string): Promise<ProjectTransition | null> {
      try {
        return await request<ProjectTransition>(`/projects/${projectId}/transition`);
      } catch {
        return null;
      }
    },
    async update(
      projectId: string,
      data: {
        name?: string;
        slug?: string;
        description?: string;
        status?: string;
        visibility?: "private" | "organisation";
        owner_id?: string;
        start_date?: string;
        target_completion_date?: string;
      }
    ): Promise<Project> {
      return request<Project>(`/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    async archive(projectId: string): Promise<Project> {
      return request<Project>(`/projects/${projectId}/archive`, {
        method: "POST",
      });
    },
    async getActivity(
      projectId: string,
      limit: number = 20,
      offset: number = 0
    ): Promise<{ items: ProjectActivityCard[]; total: number }> {
      const res = await request<{ items?: ProjectActivityCard[]; total?: number }>(
        `/projects/${projectId}/activity?limit=${limit}&offset=${offset}`
      );
      return {
        items: res?.items || [],
        total: res?.total || 0,
      };
    },
    async upsertTransition(
      projectId: string,
      data: {
        departing_user_id: string;
        successor_user_id: string;
        workflow_stage?: string;
        handover_scope?: string;
        source_scope?: string[];
        capture_start_date?: string;
        capture_end_date?: string;
        context_notes?: string;
      }
    ): Promise<ProjectTransition> {
      return request<ProjectTransition>(`/projects/${projectId}/transition`, {
        method: "PUT",
        body: JSON.stringify(data),
      });
    },
    async listInvitations(
      orgId: string,
      projectId: string,
      params?: { status?: string; limit?: number; offset?: number }
    ): Promise<InvitationListResponse> {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.limit) qs.set("limit", String(params.limit));
      if (params?.offset) qs.set("offset", String(params.offset));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request<InvitationListResponse>(
        `/organisations/${orgId}/projects/${projectId}/invitations${suffix}`
      );
    },
    async createInvitation(
      orgId: string,
      projectId: string,
      data: { email: string; role_name: string; expires_in_hours?: number }
    ): Promise<CreateInvitationResponse> {
      return request<CreateInvitationResponse>(
        `/organisations/${orgId}/projects/${projectId}/invitations`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      );
    },
    async revokeInvitation(
      orgId: string,
      projectId: string,
      invitationId: string
    ): Promise<InvitationSummary> {
      return request<InvitationSummary>(
        `/organisations/${orgId}/projects/${projectId}/invitations/${invitationId}`,
        {
          method: "DELETE",
        }
      );
    },
      async getProcessingStatus(projectId: string): Promise<ProjectProcessingStatus> {
      return request<ProjectProcessingStatus>(`/projects/${projectId}/processing-status`);
    },
    async retryProcessing(projectId: string): Promise<ProjectProcessingStatus> {
      return request<ProjectProcessingStatus>(`/projects/${projectId}/processing-status/retry`, {
        method: "POST",
      });
    },
  },

  // Project Members & Transition Roles
  members: {
    async list(projectId: string): Promise<ProjectMember[]> {
      const res = await request<unknown>(`/projects/${projectId}/members`);
      const raw = unwrapList<Record<string, unknown>>(res);
      return raw.map((m) => ({
        ...(m as unknown as ProjectMember),
        user_email: (m.user_email as string | null) || (m.email as string | null) || null,
        user_full_name: (m.user_full_name as string | null) || (m.full_name as string | null) || null,
        email: (m.email as string | null) || (m.user_email as string | null) || null,
        full_name: (m.full_name as string | null) || (m.user_full_name as string | null) || null,
      }));
    },
    async add(
      projectId: string,
      data: { user_id?: string; email?: string; role_name?: string; transition_role?: string; responsibility_description?: string }
    ): Promise<ProjectMember> {
      return request<ProjectMember>(`/projects/${projectId}/members`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async updateRole(
      projectId: string,
      userId: string,
      data: { role_name: string; responsibility_description?: string | null }
    ): Promise<ProjectMember> {
      return request<ProjectMember>(`/projects/${projectId}/members/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    async updateName(
      projectId: string,
      userId: string,
      fullName: string
    ): Promise<ProjectMember> {
      return request<ProjectMember>(`/projects/${projectId}/members/${userId}/name`, {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName }),
      });
    },
    async remove(projectId: string, userId: string): Promise<{ success: boolean; message: string }> {
      return request<{ success: boolean; message: string }>(`/projects/${projectId}/members/${userId}`, {
        method: "DELETE",
      });
    },
    async update(projectId: string, memberId: string, data: { role_name?: string; transition_role?: string }): Promise<ProjectMember> {
      return request<ProjectMember>(`/projects/${projectId}/members/${memberId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
  },

  // Sources & Connections
  sources: {
    async listOrgConnections(orgId: string): Promise<SourceConnection[]> {
      const res = await request<unknown>(`/organisations/${orgId}/sources`);
      return unwrapList<SourceConnection>(res);
    },
    async connectSource(orgId: string, data: { provider: "github" | "jira" | "slack"; access_token: string; account_identifier: string; granted_scopes?: string[] }): Promise<SourceConnection> {
      const defaultScopes =
        data.provider === "github"
          ? ["repo", "read:org"]
          : data.provider === "slack"
          ? ["channels:read", "channels:history"]
          : ["read:jira-work"];
      return request<SourceConnection>(`/organisations/${orgId}/sources`, {
        method: "POST",
        body: JSON.stringify({
          provider: data.provider,
          account_identifier: data.account_identifier.trim(),
          secret_token: data.access_token.trim(),
          access_token: data.access_token.trim(),
          scopes: data.granted_scopes || defaultScopes,
        }),
      });
    },
    async listProjectMappings(projectId: string): Promise<ProjectSourceMapping[]> {
      const res = await request<unknown>(`/projects/${projectId}/sources/mappings`);
      return unwrapList<ProjectSourceMapping>(res);
    },
    async createProjectMapping(projectId: string, data: { source_connection_id: string; external_resource_key?: string; external_resource_id?: string; external_resource_name: string; external_resource_url?: string }): Promise<ProjectSourceMapping> {
      const resId = (data.external_resource_id || data.external_resource_key || "").trim();
      return request<ProjectSourceMapping>(`/projects/${projectId}/sources/mappings`, {
        method: "POST",
        body: JSON.stringify({
          source_connection_id: data.source_connection_id,
          external_resource_id: resId,
          external_resource_key: resId,
          external_resource_name: (data.external_resource_name || resId).trim(),
        }),
      });
    },
    async triggerSync(projectId: string, mappingId: string): Promise<{ job_id: string; status: string; message: string }> {
      return request<{ job_id: string; status: string; message: string }>(
        `/projects/${projectId}/sources/mappings/${mappingId}/sync`,
        { method: "POST" }
      );
    },
    async getSyncJobs(projectId: string, mappingId: string): Promise<Record<string, unknown>[]> {
      const res = await request<unknown>(`/projects/${projectId}/sources/mappings/${mappingId}/jobs`);
      return unwrapList<Record<string, unknown>>(res);
    },
    async discoverGitHubRepositories(connectionId: string, page = 1, perPage = 50, projectId?: string): Promise<{ connection_id: string; items: Array<{ external_resource_id: string; full_name: string; name: string; owner_login: string; description?: string; default_branch?: string; visibility: string; is_private: boolean; html_url?: string; updated_at?: string; language?: string; topics?: string[]; created_at?: string; pushed_at?: string; is_fork?: boolean; is_archived?: boolean; is_disabled?: boolean; open_issues_count?: number; already_mapped?: boolean }>; page: number; per_page: number; has_next_page: boolean }> {
      const pIdQuery = projectId ? `&project_id=${encodeURIComponent(projectId)}` : "";
      return request(`/integrations/connections/${connectionId}/github/repositories?page=${page}&per_page=${perPage}${pIdQuery}`);
    },
    async discoverJiraSites(connectionId: string): Promise<{ connection_id: string; items: Array<{ cloud_id: string; name: string; url?: string; scopes: string[] }>; total: number }> {
      return request(`/integrations/connections/${connectionId}/jira/sites`);
    },
    async discoverJiraProjects(connectionId: string, cloudId?: string): Promise<{ connection_id: string; sites: Array<{ cloud_id: string; name: string }>; selected_cloud_id?: string; projects: Array<{ cloud_id: string; external_resource_id: string; key: string; name: string; project_type_key?: string; url?: string; is_private?: boolean }>; total: number }> {
      const qs = cloudId ? `?cloud_id=${encodeURIComponent(cloudId)}` : "";
      return request(`/integrations/connections/${connectionId}/jira/projects${qs}`);
    },
    async discoverSlackChannels(connectionId: string): Promise<{ connection_id: string; items: Array<{ id: string; name: string; is_private: boolean; is_archived: boolean; num_members: number; topic: string; purpose: string }>; total: number }> {
      return request(`/integrations/connections/${connectionId}/slack/channels`);
    },
    async createGitHubMapping(projectId: string, data: { source_connection_id: string; owner: string; repo: string; include_issues?: boolean; include_pull_requests?: boolean; include_commits?: boolean; include_docs?: boolean }): Promise<ProjectSourceMapping> {
      return request(`/projects/${projectId}/integrations/github/mappings`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async createJiraMapping(projectId: string, data: { source_connection_id: string; cloud_id: string; project_key: string; include_comments?: boolean; include_worklogs?: boolean; include_links?: boolean; include_changelog?: boolean }): Promise<ProjectSourceMapping> {
      return request(`/projects/${projectId}/integrations/jira/mappings`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async createSlackMapping(projectId: string, data: { source_connection_id: string; channel_id: string; channel_name: string; include_threads?: boolean; include_files?: boolean }): Promise<ProjectSourceMapping> {
      return request(`/projects/${projectId}/integrations/slack/mappings`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async batchCreateMappings(projectId: string, data: { provider: string; source_connection_id: string; items: Array<Record<string, unknown>> }): Promise<{ created_mappings: ProjectSourceMapping[]; failed_count: number; errors: string[] }> {
      return request(`/projects/${projectId}/integrations/batch-mappings`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  },

  // Evidence Workspace
  evidence: {
    async list(projectId: string, params: { q?: string; provider?: string; limit?: number; offset?: number } = {}): Promise<EvidenceSummary[]> {
      const query = new URLSearchParams();
      if (params.q) query.append("q", params.q);
      if (params.provider && params.provider !== "all") query.append("provider", params.provider);
      if (params.limit) {
        const safeLimit = Math.min(params.limit, 100);
        query.append("limit", safeLimit.toString());
      }
      if (params.offset) query.append("offset", params.offset.toString());
      const qs = query.toString() ? `?${query.toString()}` : "";
      const res = await request<unknown>(`/projects/${projectId}/evidence${qs}`);
      return unwrapList<EvidenceSummary>(res);
    },
    async getMetrics(projectId: string): Promise<EvidenceMetrics> {
      return request<EvidenceMetrics>(`/projects/${projectId}/evidence/metrics`);
    },
    async getDetail(evidenceId: string): Promise<EvidenceDetail> {
      return request<EvidenceDetail>(`/evidence/${evidenceId}`);
    },
    async upload(projectId: string, file: File, options?: { title?: string; document_category?: string; document_subtype?: string; custom_title?: string } | string): Promise<{ document_id: string; evidence_item_id?: string; title: string; processing_status: string }> {
      const formData = new FormData();
      formData.append("file", file);
      if (typeof options === "string") {
        if (options) formData.append("custom_title", options);
      } else if (options) {
        const titleVal = options.custom_title || options.title;
        if (titleVal) formData.append("custom_title", titleVal);
        if (options.document_category) formData.append("document_category", options.document_category);
        if (options.document_subtype) formData.append("document_subtype", options.document_subtype);
      }
      return request<{ document_id: string; evidence_item_id?: string; title: string; processing_status: string }>(
        `/projects/${projectId}/evidence/upload`,
        {
          method: "POST",
          body: formData,
        }
      );
    },
    async download(evidenceId: string): Promise<Blob> {
      const url = `${API_BASE_URL}/evidence/${evidenceId}/download`;
      const token = getToken();
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        throw new ApiError(`Download failed with status ${res.status}`, res.status);
      }
      return res.blob();
    },
    async reprocess(projectId: string, evidenceId: string): Promise<unknown> {
      return request<unknown>(`/projects/${projectId}/evidence/${evidenceId}/reprocess`, {
        method: "POST",
      });
    },
      async extract(projectId: string, evidenceId: string): Promise<unknown> {
      return request<unknown>(`/projects/${projectId}/evidence/${evidenceId}/extract`, {
        method: "POST",
      });
    },
  },

  // Persistent Notifications & Active Tasks
  notifications: {
    async list(
      paramsOrProjectId?:
        | string
        | {
            type?: import("./types").NotificationType;
            unread_only?: boolean;
            project_id?: string;
            limit?: number;
            offset?: number;
          },
      unreadOnly = false
    ): Promise<any> {
      const query = new URLSearchParams();
      if (typeof paramsOrProjectId === "string") {
        if (paramsOrProjectId) query.append("project_id", paramsOrProjectId);
        if (unreadOnly) query.append("unread_only", "true");
      } else if (paramsOrProjectId) {
        if (paramsOrProjectId.type) query.set("type", paramsOrProjectId.type);
        if (paramsOrProjectId.unread_only) query.set("unread_only", "true");
        if (paramsOrProjectId.project_id) query.set("project_id", paramsOrProjectId.project_id);
        if (paramsOrProjectId.limit !== undefined) query.set("limit", String(paramsOrProjectId.limit));
        if (paramsOrProjectId.offset !== undefined) query.set("offset", String(paramsOrProjectId.offset));
      }
      const qs = query.toString() ? `?${query.toString()}` : "";
      return request(`/notifications${qs}`);
    },
    async markRead(notificationId: string, isRead: boolean = true): Promise<unknown> {
      return request(`/notifications/${notificationId}/read`, {
        method: "PATCH",
        body: JSON.stringify({ is_read: isRead }),
      });
    },
    async markAllRead(projectId?: string): Promise<{ marked_read?: number; updated_count?: number }> {
      return request(`/notifications/mark-all-read`, {
        method: "POST",
        body: JSON.stringify(projectId ? { project_id: projectId } : {}),
      });
    },
    async listActiveJobs(projectId: string): Promise<Array<{ id: string; project_id: string; job_type: string; status: string; stage?: string; progress_percent: number; attempt_count: number; message?: string; created_at: string; started_at?: string }>> {
      const res = await request<unknown>(`/projects/${projectId}/jobs/active`);
      return unwrapList(res);
    },
    async getPreferences(): Promise<import("./types").NotificationPreferences> {
      return request("/notifications/preferences");
    },
    async updatePreferences(
      data: Partial<Omit<import("./types").NotificationPreferences, "user_id" | "updated_at">>
    ): Promise<import("./types").NotificationPreferences> {
      return request("/notifications/preferences", {
        method: "PUT",
        body: JSON.stringify(data),
      });
    },
  },

  // Team Roster & Contribution Attribution
  roster: {
    async listMembers(projectId: string, evidenceId?: string, status?: string): Promise<Array<{ id: string; project_id: string; evidence_item_id: string; member_id_in_roster?: string; full_name: string; email?: string; role_name?: string; primary_responsibilities: string[]; component_ownership: string[]; github_username?: string; git_commit_email?: string; reconciliation_status: string; matched_project_membership_id?: string; matched_member_name?: string; reconciliation_confidence?: number; reconciliation_notes?: string; created_at: string }>> {
      const query = new URLSearchParams();
      if (evidenceId) query.append("evidence_id", evidenceId);
      if (status) query.append("status", status);
      const qs = query.toString() ? `?${query.toString()}` : "";
      const res = await request<unknown>(`/projects/${projectId}/roster/members${qs}`);
      return unwrapList(res);
    },
    async reconcile(projectId: string, memberId: string, data: { reconciliation_status: string; matched_project_membership_id?: string; reconciliation_notes?: string }): Promise<unknown> {
      return request(`/projects/${projectId}/roster/members/${memberId}/reconcile`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    async listAttributions(projectId: string, evidenceId?: string, category?: string): Promise<Array<{ id: string; project_id: string; evidence_item_id: string; contributor_identifier: string; identifier_type: string; matched_roster_member_id?: string; matched_roster_name?: string; matched_project_membership_id?: string; match_method?: string; match_confidence?: number; contribution_category?: string; responsibility_alignment?: string; alignment_explanation?: string; created_at: string }>> {
      const query = new URLSearchParams();
      if (evidenceId) query.append("evidence_id", evidenceId);
      if (category) query.append("category", category);
      const qs = query.toString() ? `?${query.toString()}` : "";
      const res = await request<unknown>(`/projects/${projectId}/roster/attributions${qs}`);
      return unwrapList(res);
    },
  },
  relationships: {

    async getGraph(

      projectId: string,

      limit: number = 250,

      options?: { center_node_id?: string; depth?: number; entity_type?: string }

    ): Promise<{

      nodes: Array<{

        id: string;

        label: string;

        type?: string;

        entity_type?: string;

        canonical_name?: string;

        description?: string | null;

        confidence?: number;

        resolution_status?: string;

        status?: string;

        verification_status?: string;

        source_provider?: string | null;

      }>;

      edges: Array<{

        id: string;

        source: string;

        target: string;

        type?: string;

        relationship_type?: string;

        label?: string;

        verification_status?: string;

        confidence?: number;

        evidence_count?: number;

      }>;

      total_nodes?: number;

      total_edges?: number;

    }> {

      const qs = new URLSearchParams({

        limit_nodes: String(limit),

        limit_edges: String(limit * 2),

      });

      if (options?.center_node_id) qs.set("center_node_id", options.center_node_id);

      if (options?.depth) qs.set("depth", String(options.depth));

      if (options?.entity_type) qs.set("entity_type", options.entity_type);

      return request(`/projects/${projectId}/relationships/graph?${qs.toString()}`);

    },

    async listEntities(projectId: string, type?: string, page: number = 1, pageSize: number = 50): Promise<{

      items: Array<{

        id: string;

        canonical_name: string;

        entity_type: string;

        confidence_score: number;

        resolution_status: string;

        description?: string;

        created_at: string;

      }>;

      total: number;

    }> {

      const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });

      if (type) qs.append("type", type);

      return request(`/projects/${projectId}/relationships/entities?${qs.toString()}`);

    },

    async getEntityDetails(projectId: string, entityId: string): Promise<Record<string, unknown>> {

      return request(`/projects/${projectId}/relationships/entities/${entityId}`);

    },

    async getTraceability(projectId: string): Promise<{

      items?: Array<{

        id: string;

        decision_entity_id: string;

        decision_name?: string;

        completeness_status: string;

        work_item_count?: number;

        pr_count?: number;

        commit_count?: number;

        component_count?: number;

        work_item_ids?: string[];

        pull_request_ids?: string[];

        commit_ids?: string[];

        component_ids?: string[];

        missing_links: string[];

      }>;

      chains?: Array<{

        id: string;

        decision_entity_id: string;

        decision_name: string;

        completeness_status: string;

        work_item_count: number;

        pr_count: number;

        commit_count: number;

        component_count: number;

        missing_links: string[];

      }>;

    }> {

      return request(`/projects/${projectId}/relationships/traceability`);

    },

    async getDependencies(projectId: string, rootId?: string): Promise<{

      nodes: Array<{ id: string; label: string; entity_type: string; is_root_blocker: boolean; in_degree: number; out_degree: number }>;

      edges: Array<{ source: string; target: string; relationship_type: string }>;

      cycles: string[][];

      detected_cycles?: string[][];

      root_blockers: string[];

    }> {

      const qs = rootId ? `?root_entity_id=${rootId}` : "";

      return request(`/projects/${projectId}/relationships/dependencies${qs}`);

    },

    async getTimeline(projectId: string): Promise<{

      items: Array<{

        id: string;

        event_type: string;

        title: string;

        summary?: string;

        occurred_at: string;

        timestamp_precision: string;

        timestamp_origin: string;

      }>;

      total_events: number;

    }> {

      return request(`/projects/${projectId}/relationships/timeline`);

    },

    async listIdentityCandidates(projectId: string): Promise<Record<string, unknown>[]> {

      return request(`/projects/${projectId}/relationships/identities/candidates`);

    },

    async reviewCandidate(projectId: string, candidateId: string, decision: "accept" | "reject", rationale?: string): Promise<Record<string, unknown>> {

      return request(`/projects/${projectId}/relationships/identities/candidates/${candidateId}/review`, {

        method: "POST",
        body: JSON.stringify({ action: decision, decision, rationale }),
      });

    },

    async triggerReconstruction(projectId: string): Promise<{

      id: string;

      status: string;

      entities_discovered: number;

      relationships_discovered: number;

    }> {

      return request(`/projects/${projectId}/relationships/reconstruct`, {

        method: "POST",

      });

    },

    async submitRelationshipReview(

      projectId: string,

      relationshipId: string,

      payload: { action: "verify" | "reject" | "dispute" | "request_evidence"; note?: string }

    ): Promise<Record<string, unknown>> {

      return request(`/projects/${projectId}/relationships/${relationshipId}/submit-for-review`, {

        method: "POST",

        body: JSON.stringify(payload),

      });

    },

    async getContributorsGraph(

      projectId: string,

      params?: {

        contributor_type?: string;

        work_cluster?: string;

        repository?: string;

        verification_state?: string;

        search?: string;

        include_external?: boolean;

        include_bots?: boolean;

        expand_contributor_key?: string;

        expand_cluster_name?: string;

        limit?: number;

      }

    ): Promise<{

      project_id: string;

      nodes: Array<{

        id: string;

        node_kind: string;

        label: string;

        contributor_key?: string | null;

        contributor_type: string;

        review_status: string;

        verification_status: string;

        contribution_count: number;

        metadata: Record<string, unknown>;

      }>;

      edges: Array<{

        id: string;

        source: string;

        target: string;

        relationship_type: string;

        label: string;

        evidence_basis: string;

      }>;

      summary: Record<string, number>;

    }> {

      const qs = new URLSearchParams();

      if (params) {

        Object.entries(params).forEach(([k, v]) => {

          if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));

        });

      }

      const suffix = qs.toString() ? `?${qs.toString()}` : "";

      return request(`/projects/${projectId}/relationships/contributors/graph${suffix}`);

    },

    async listContributors(

      projectId: string,

      params?: { contributor_type?: string; review_status?: string }

    ): Promise<

      Array<{

        contributor_key: string;

        display_name: string;

        github_login?: string | null;

        github_numeric_id?: string | null;

        git_author_name?: string | null;

        git_author_email?: string | null;

        contributor_type: string;

        review_status: string;

        match_method?: string | null;

        match_confidence?: number | null;

        matched_project_membership_id?: string | null;

        matched_member_name?: string | null;

        suggested_project_membership_id?: string | null;

        suggested_member_name?: string | null;

        declared_responsibility?: string | null;

        contribution_count: number;

        commits_count: number;

        prs_count: number;

        issues_count: number;

        repositories: string[];

        work_areas: string[];

        evidence_ids: string[];

        review_history: Array<Record<string, unknown>>;

      }>

    > {

      const qs = new URLSearchParams();

      if (params?.contributor_type) qs.set("contributor_type", params.contributor_type);

      if (params?.review_status) qs.set("review_status", params.review_status);

      const suffix = qs.toString() ? `?${qs.toString()}` : "";

      return request(`/projects/${projectId}/relationships/contributors${suffix}`);

    },

    async getContributorDetail(projectId: string, contributorKey: string): Promise<Record<string, unknown>> {

      return request(`/projects/${projectId}/relationships/contributors/${encodeURIComponent(contributorKey)}`);

    },

    async listSelectableMembers(projectId: string): Promise<

      Array<{

        selection_key: string;

        member_source: string;

        membership_state: string;

        selectable_for_match: boolean;

        project_membership_id?: string | null;

        user_id?: string | null;

        invitation_id?: string | null;

        roster_member_id?: string | null;

        display_name: string;

        email?: string | null;

        role_name: string;

        github_login?: string | null;

        review_status: string;

        note?: string | null;

      }>

    > {

      return request(`/projects/${projectId}/relationships/identities/selectable-members`);

    },

    async reviewContributor(

      projectId: string,

      contributorKey: string,

      payload: {

        action: "match_member" | "mark_external" | "mark_bot" | "leave_unidentified" | "reject_match" | "revert";

        project_membership_id?: string;

        user_id?: string;

        invitation_id?: string;

        roster_member_id?: string;

        notes?: string;

      }

    ): Promise<{ contributor_key: string; contributor_type: string; review_status: string; updated_records: number }> {

      return request(`/projects/${projectId}/relationships/contributors/${encodeURIComponent(contributorKey)}/review`, {

        method: "POST",

        body: JSON.stringify(payload),

      });

    },

    async listWorkClusters(projectId: string): Promise<

      Array<{

        cluster_id: string;

        name: string;

        classification_method: string;

        contribution_count: number;

        contributor_count: number;

        contributors: Array<{ contributor_key: string; display_name: string; contributor_type: string; count: number }>;

        contributions: Array<{

          evidence_id: string;

          title: string;

          category: string;

          contributor_key: string;

          contributor_name: string;

          contributor_type: string;

          alignment?: string | null;

        }>;

        changed_paths: string[];

        evidence_ids: string[];

      }>

    > {

      return request(`/projects/${projectId}/relationships/work-clusters`);

    },

    async rebuildWorkClusters(projectId: string): Promise<{

      run_id: string;

      algorithm_version: string;

      clusters_count: number;

      relationships_created: number;

      completed_at: string;

    }> {

      return request(`/projects/${projectId}/relationships/work-clusters/rebuild`, {

        method: "POST",

      });

    },

  },
  knowledgeIntelligence: {
    async getQuality(projectId: string, refresh: boolean = false): Promise<{
      project_id?: string;
      dimension_scores: Record<string, number>;
      overall_quality_score?: number;
      overall_score?: number;
      identified_gaps?: Array<{
        type: string;
        severity: string;
        title: string;
        description: string;
        recommendation: string;
      }>;
      gaps?: Array<{
        type: string;
        severity: string;
        title: string;
        description: string;
        recommendation: string;
      }>;
      total_items: number;
      verified_items?: number;
      stale_items?: number;
      recommendation_count?: number;
    }> {
      const q = refresh ? "?sync_findings=true" : "";
      return request(`/projects/${projectId}/knowledge-intelligence/quality${q}`);
    },

    async getGraph(

      projectId: string,

      graphType: "technology-stack" | "system-architecture" | "features-workflows",

      params?: {

        search?: string;

        status?: string;

        source_type?: string;

        verification_state?: string;

        limit?: number;

        cursor?: string;

        include_suggested?: boolean;

      }

    ): Promise<{

      graph_type: "technology-stack" | "system-architecture" | "features-workflows";

      project_id: string;

      nodes: Array<{

        id: string;

        entity_type: string;

        label: string;

        description?: string | null;

        category?: string | null;

        status: string;

        verification_status: string;

        evidence_count: number;

        evidence_ids: string[];

        aliases: string[];

        last_observed_at?: string | null;

        metadata: Record<string, unknown>;

      }>;

      edges: Array<{

        id: string;

        source: string;

        target: string;

        relationship_type: string;

        label: string;

        evidence_basis: string;

        verification_status: string;

        confidence_score: number;

        evidence_ids: string[];

      }>;

      summary: { node_count: number; edge_count: number; categories: Record<string, number> };

      next_cursor?: string | null;

    }> {

      const qs = new URLSearchParams();

      if (params) {

        Object.entries(params).forEach(([k, v]) => {

          if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));

        });

      }

      const suffix = qs.toString() ? `?${qs.toString()}` : "";

      return request(`/projects/${projectId}/knowledge-intelligence/graphs/${graphType}${suffix}`);

    },

    async getGraphNodeDetail(

      projectId: string,

      graphType: "technology-stack" | "system-architecture" | "features-workflows",

      nodeId: string

    ): Promise<{

      graph_type: string;

      project_id: string;

      node: Record<string, unknown>;

      adjacent_edges: Array<Record<string, unknown>>;

      related_nodes: Array<Record<string, unknown>>;

      evidence_refs: Array<{

        evidence_id: string;

        title: string;

        source_type: string;

        source_url?: string | null;

        supporting_excerpt?: string | null;

      }>;

    }> {

      return request(`/projects/${projectId}/knowledge-intelligence/graphs/${graphType}/nodes/${nodeId}`);

    },

    async getSummary(projectId: string): Promise<{

      total_findings: number;

      by_category: Record<string, number>;

      by_domain: Record<string, number>;

      verified_count: number;

      candidate_count: number;

    }> {

      return request(`/projects/${projectId}/knowledge-intelligence/summary`);

    },

    async getDomains(projectId: string): Promise<{

      domains: Array<{

        domain_id: string;

        display_name: string;

        description: string;

        item_count: number;

        verified_count: number;

        pending_review_count: number;

        completeness_score: number;

      }>;

      total_domains: number;

      active_domains_count: number;

    }> {

      return request(`/projects/${projectId}/knowledge-intelligence/domains`);

    },

    async triggerExtraction(projectId: string, options?: { domains?: string[]; evidence_ids?: string[]; force_rerun?: boolean }): Promise<{

      run: Record<string, unknown>;

      job?: Record<string, unknown>;

      already_active: boolean;

    }> {

      return request(`/projects/${projectId}/knowledge-intelligence/extract`, {

        method: "POST",

        body: JSON.stringify(options || {}),

      });

    },

    async listFindings(

      projectId: string,

      domain?: string,

      limit: number = 100,

      offset: number = 0

    ): Promise<{

      items: Record<string, unknown>[];

      total: number;

      limit: number;

      offset: number;

    }> {

      const qs = new URLSearchParams({

        limit: String(Math.min(limit, 100)),

        offset: String(offset),

      });

      if (domain) qs.append("domain", domain);

      return request(`/projects/${projectId}/knowledge-intelligence/findings?${qs.toString()}`);

    },

  },

    knowledge: {

    async triggerEvidenceExtraction(

      projectId: string,

      evidenceId: string,

      payload?: { categories?: string[]; force_rerun?: boolean }

    ): Promise<{

      run: Record<string, unknown>;

      job?: Record<string, unknown>;

      already_active: boolean;

    }> {

      return request(`/projects/${projectId}/evidence/${evidenceId}/extractions`, {

        method: "POST",

        body: JSON.stringify(payload || {}),

      });

    },

    async listEvidenceExtractions(

      projectId: string,

      evidenceId: string,

      status?: string

    ): Promise<{

      items: Record<string, unknown>[];

      total: number;

    }> {

      const qs = new URLSearchParams();

      if (status) qs.append("status", status);

      const qStr = qs.toString() ? `?${qs.toString()}` : "";

      return request(`/projects/${projectId}/evidence/${evidenceId}/extractions${qStr}`);

    },

    async getEvidenceExtraction(

      projectId: string,

      evidenceId: string,

      runId: string

    ): Promise<Record<string, unknown>> {

      return request(`/projects/${projectId}/evidence/${evidenceId}/extractions/${runId}`);

    },

    async getEvidenceFacts(

      projectId: string,

      evidenceId: string

    ): Promise<{

      evidence_id: string;

      project_id: string;

      total_facts: number;

      ai_extracted_count: number;

      raw_chunk_count: number;

      latest_run_id?: string | null;

      latest_run_status?: string | null;

      facts: Array<{

        id: string;

        evidence_id: string;

        knowledge_item_id?: string | null;

        chunk_id?: string | null;

        title: string;

        description: string;

        category: string;

        primary_domain?: string | null;

        confidence_level: string;

        grounding_score: number;

        confidence_explanation?: string | null;

        original_excerpt: string;

        page_or_section?: string | null;

        validation_state: string;

        is_ai_extracted: boolean;

        created_at: string;

      }>;

      raw_chunks: Array<{

        id: string;

        chunk_index: number;

        page_number?: number | null;

        chunk_type: string;

        char_count: number;

        token_estimate: number;

        chunk_text: string;

        text_content?: string;

        indexing_status: string;

      }>;

    }> {

      return request(`/projects/${projectId}/evidence/${evidenceId}/facts`);

    },

    async getEvidenceFindings(

      projectId: string,

      evidenceId: string,

      category?: string

    ): Promise<{

      items: Record<string, unknown>[];

      total: number;

    }> {

      const qs = new URLSearchParams();

      if (category) qs.append("category", category);

      const qStr = qs.toString() ? `?${qs.toString()}` : "";

      return request(`/projects/${projectId}/evidence/${evidenceId}/findings${qStr}`);

    },

  },
  verification: {
    async getSummary(projectId: string): Promise<VerificationSummaryResponse> {
      return request<VerificationSummaryResponse>(`/projects/${projectId}/verification/summary`);
    },
    async getQueue(
      projectId: string,
      filtersOrStatus?: string | QueueFilterParams,
      page: number = 1
    ): Promise<VerificationQueueResponse> {
      const qs = new URLSearchParams();

      if (typeof filtersOrStatus === "string") {
        if (filtersOrStatus && filtersOrStatus !== "all") qs.append("status", filtersOrStatus);
        qs.append("page", String(page));
      } else if (filtersOrStatus) {
        if (filtersOrStatus.status && filtersOrStatus.status !== "all") qs.append("status", filtersOrStatus.status);
        if (filtersOrStatus.case_status && filtersOrStatus.case_status !== "all") qs.append("case_status", filtersOrStatus.case_status);
        if (filtersOrStatus.priority && filtersOrStatus.priority !== "all") qs.append("priority", filtersOrStatus.priority);
        if (filtersOrStatus.target_type && filtersOrStatus.target_type !== "all") qs.append("target_type", filtersOrStatus.target_type);
        if (filtersOrStatus.assigned_reviewer_id) qs.append("assigned_reviewer_id", filtersOrStatus.assigned_reviewer_id);
        if (filtersOrStatus.unassigned_only) qs.append("unassigned_only", "true");
        if (filtersOrStatus.search) qs.append("search", filtersOrStatus.search);
        if (filtersOrStatus.limit !== undefined) qs.append("limit", String(filtersOrStatus.limit));
        if (filtersOrStatus.offset !== undefined) qs.append("offset", String(filtersOrStatus.offset));
        if (filtersOrStatus.page !== undefined) qs.append("page", String(filtersOrStatus.page));
      } else {
        qs.append("page", String(page));
      }

      return request<VerificationQueueResponse>(`/projects/${projectId}/verification/queue?${qs.toString()}`);
    },
    async getCaseDetail(projectId: string, caseId: string): Promise<VerificationCaseDetail> {
      return request<VerificationCaseDetail>(`/projects/${projectId}/verification/cases/${caseId}`);
    },
    async getCaseEvidence(projectId: string, caseId: string): Promise<CaseEvidenceResponse> {
      return request<CaseEvidenceResponse>(`/projects/${projectId}/verification/cases/${caseId}/evidence`);
    },
    async requestContext(
      projectId: string,
      caseId: string,
      payload: {
        requested_from_user_id: string;
        question: string;
        requested_information_type?: string;
        expected_version?: number;
      }
    ): Promise<VerificationContextRequest> {
      return request<VerificationContextRequest>(`/projects/${projectId}/verification/cases/${caseId}/request-context`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    async listUserContextRequests(projectId: string, status?: string): Promise<VerificationContextRequest[]> {
      const q = status ? `?status_filter=${encodeURIComponent(status)}` : "";
      return request<VerificationContextRequest[]>(`/projects/${projectId}/verification/context-requests${q}`);
    },
    async respondContextRequest(
      projectId: string,
      requestId: string,
      payload: { response_text: string; response_evidence_id?: string }
    ): Promise<VerificationContextRequest> {
      return request<VerificationContextRequest>(
        `/projects/${projectId}/verification/context-requests/${requestId}/respond`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
    },
    async approveCase(
      projectId: string,
      caseId: string,
      optionsOrVersion?: number | { expected_version?: number; review_notes?: string; notes?: string } | string,
      maybeNotes?: string
    ): Promise<VerificationCaseDetail> {
      let body: { expected_version?: number; review_notes: string; notes: string };

      if (typeof optionsOrVersion === "object" && optionsOrVersion !== null) {
        const revNotes = optionsOrVersion.review_notes || optionsOrVersion.notes || "Approved in Verification Center review";
        body = {
          expected_version: optionsOrVersion.expected_version,
          review_notes: revNotes,
          notes: revNotes,
        };
      } else if (typeof optionsOrVersion === "number") {
        const revNotes = maybeNotes || "Approved in Verification Center review";
        body = {
          expected_version: optionsOrVersion,
          review_notes: revNotes,
          notes: revNotes,
        };
      } else {
        const revNotes = optionsOrVersion || maybeNotes || "Approved in Verification Center review";
        body = {
          review_notes: revNotes,
          notes: revNotes,
        };
      }

      return request<VerificationCaseDetail>(`/projects/${projectId}/verification/cases/${caseId}/approve`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    async rejectCase(
      projectId: string,
      caseId: string,
      optionsOrVersion?: number | { expected_version?: number; reason: string; review_notes?: string; notes?: string } | string,
      maybeReason?: string,
      maybeNotes?: string
    ): Promise<VerificationCaseDetail> {
      let body: { expected_version?: number; reason: string; review_notes?: string; notes?: string };

      if (typeof optionsOrVersion === "object" && optionsOrVersion !== null) {
        const revNotes = optionsOrVersion.review_notes || optionsOrVersion.notes;
        body = {
          expected_version: optionsOrVersion.expected_version,
          reason: optionsOrVersion.reason || "Rejected by reviewer",
          review_notes: revNotes,
          notes: revNotes,
        };
      } else if (typeof optionsOrVersion === "number") {
        body = {
          expected_version: optionsOrVersion,
          reason: maybeReason || "Rejected by reviewer",
          review_notes: maybeNotes,
          notes: maybeNotes,
        };
      } else {
        body = {
          reason: optionsOrVersion || maybeReason || "Rejected by reviewer",
          review_notes: maybeReason && maybeNotes ? maybeNotes : (maybeReason || undefined),
          notes: maybeReason && maybeNotes ? maybeNotes : (maybeReason || undefined),
        };
      }

      return request<VerificationCaseDetail>(`/projects/${projectId}/verification/cases/${caseId}/reject`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    async markUnresolved(
      projectId: string,
      caseId: string,
      optionsOrReason: string | { expected_version?: number; explanation?: string; reason?: string },
      expectedVersion?: number
    ): Promise<VerificationCaseDetail> {
      let body: { expected_version?: number; explanation: string; reason?: string };

      if (typeof optionsOrReason === "object" && optionsOrReason !== null) {
        body = {
          expected_version: optionsOrReason.expected_version,
          explanation: optionsOrReason.explanation || optionsOrReason.reason || "Unresolved - consensus not established",
          reason: optionsOrReason.reason,
        };
      } else {
        body = {
          expected_version: expectedVersion,
          explanation: optionsOrReason || "Unresolved - consensus not established",
          reason: optionsOrReason,
        };
      }

      return request<VerificationCaseDetail>(`/projects/${projectId}/verification/cases/${caseId}/mark-unresolved`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    async reviewFinding(
      projectId: string,
      findingId: string,
      payload: { action: "approve" | "flag" | "reject"; notes?: string }
    ): Promise<Record<string, unknown>> {
      return request(
        `/projects/${projectId}/verification/findings/${findingId}/review`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
    },
    async editFinding(
      projectId: string,
      caseId: string,
      payload: {
        expected_version: number;
        title?: string;
        summary?: string;
        patch_data?: Record<string, unknown>;
        reason?: string;
      }
    ): Promise<VerificationCaseDetail> {
      return request<VerificationCaseDetail>(`/projects/${projectId}/verification/cases/${caseId}/finding`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_version: payload.expected_version,
          patch_data: payload.patch_data || {
            title: payload.title,
            summary: payload.summary,
          },
          title: payload.title,
          summary: payload.summary,
          reason: payload.reason || "Auditor correction",
        }),
      });
    },
    async assignReviewer(
      projectId: string,
      caseId: string,
      assigneeOrPayload: string | null | { expected_version: number; assignee_user_id: string | null },
      expectedVersion?: number
    ): Promise<VerificationCaseDetail> {
      let body: { expected_version: number; assignee_user_id: string | null };

      if (typeof assigneeOrPayload === "object" && assigneeOrPayload !== null) {
        body = assigneeOrPayload;
      } else {
        body = {
          expected_version: expectedVersion ?? 1,
          assignee_user_id: assigneeOrPayload,
        };
      }

      return request<VerificationCaseDetail>(`/projects/${projectId}/verification/cases/${caseId}/assign`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    async getHandoverEligibility(projectId: string, caseId: string): Promise<HandoverEligibilityResponse> {
      return request<HandoverEligibilityResponse>(`/projects/${projectId}/verification/cases/${caseId}/eligibility`);
    },
    async assess(projectId: string, targetType: "knowledge_item" | "relationship", targetId: string): Promise<VerificationCaseDetail> {
      return request<VerificationCaseDetail>(
        `/projects/${projectId}/verification/assess?target_type=${targetType}&target_id=${targetId}`,
        { method: "POST" }
      );
    },
    async ensureTargetCase(
      projectId: string,
      targetType: "knowledge_item" | "relationship",
      targetId: string
    ): Promise<{ id: string; version: number; case_status: string }> {
      return request<{ id: string; version: number; case_status: string }>(
        `/projects/${projectId}/verification/target-case?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`,
        { method: "POST" }
      );
    },
    async assessTarget(
      projectId: string,
      targetType: "knowledge_item" | "relationship",
      targetId: string
    ): Promise<VerificationCaseDetail> {
      return request<VerificationCaseDetail>(
        `/projects/${projectId}/verification/assess?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`,
        { method: "POST" }
      );
    },
    async assessAll(projectId: string): Promise<VerificationSummaryResponse> {
      return request<VerificationSummaryResponse>(`/projects/${projectId}/verification/assess-all`, {
        method: "POST",
      });
    },
    async getChangeImpact(
      projectId: string,
      limit: number = 50,
      offset: number = 0
    ): Promise<ChangeImpactFeedResponse> {
      return request<ChangeImpactFeedResponse>(
        `/projects/${projectId}/verification/change-impact?limit=${limit}&offset=${offset}`
      );
    },
  },
  conflicts: {
    async getSummary(projectId: string): Promise<ConflictSummaryResponse> {
      return request<ConflictSummaryResponse>(`/projects/${projectId}/conflicts/summary`);
    },
    async list(
      projectId: string,
      resolutionState?: string,
      conflictType?: string,
      limit: number = 50,
      offset: number = 0
    ): Promise<ConflictListResponse> {
      const qs = new URLSearchParams();
      if (resolutionState && resolutionState !== "all") qs.append("resolution_state", resolutionState);
      if (conflictType && conflictType !== "all") qs.append("conflict_type", conflictType);
      qs.append("limit", limit.toString());
      qs.append("offset", offset.toString());
      return request<ConflictListResponse>(`/projects/${projectId}/conflicts?${qs.toString()}`);
    },
    async resolve(
      projectId: string,
      conflictId: string,
      payload: {
        resolution_state: string;
        resolution_notes: string;
        preferred_claim?: string;
      }
    ): Promise<VerificationConflictItem> {
      return request<VerificationConflictItem>(`/projects/${projectId}/conflicts/${conflictId}/resolve`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    async detect(projectId: string): Promise<DetectConflictsResponse> {
      return request<DetectConflictsResponse>(`/projects/${projectId}/conflicts/detect`, {
        method: "POST",
      });
    },
  },
  handover: {
    async listCases(projectId: string, status?: string): Promise<{
      items: Array<{
        id: string;
        project_id: string;
        title: string;
        status: string;
        version: number;
        created_at: string;
        updated_at: string;
        departing_member_id?: string;
        successor_id?: string;
        assigned_reviewer_id?: string | null;
        target_handover_date?: string | null;
        handover_type?: string;
        metadata_json?: Record<string, unknown>;
      }>;
      total: number;
    }> {
      const q = status ? `?status=${encodeURIComponent(status)}` : "";
      return request(`/projects/${projectId}/handover/cases${q}`);
    },
    async createCase(projectId: string, data: {
      title: string;
      description?: string;
      departing_member_id: string;
      successor_id?: string;
      handover_type?: string;
      target_handover_date?: string | null;
      metadata_json?: Record<string, unknown>;
    }): Promise<{
      id: string;
      title: string;
      status: string;
      version: number;
      handover_type?: string;
      target_handover_date?: string | null;
      created_at: string;
      updated_at: string;
    }> {
      return request(`/projects/${projectId}/handover/cases`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async getCase(projectId: string, caseId: string): Promise<{
      case: {
        id: string;
        project_id: string;
        title: string;
        description?: string;
        status: string;
        version: number;
        departing_member_id?: string;
        successor_id?: string;
        assigned_reviewer_id?: string | null;
        handover_type?: string;
        target_handover_date?: string | null;
        metadata_json?: Record<string, unknown>;
        created_at: string;
        updated_at: string;
      };
      packages: Array<any>;
      current_version?: any;
      signoffs: Array<any>;
      status_history: Array<any>;
      responsibility_transfers: Array<any>;
    }> {
      return request(`/projects/${projectId}/handover/cases/${caseId}`);
    },
    async updateCase(
      projectId: string,
      caseId: string,
      data: {
        title?: string;
        description?: string;
        successor_id?: string;
        handover_type?: string;
        target_handover_date?: string | null;
      }
    ): Promise<any> {
      return request(`/projects/${projectId}/handover/cases/${caseId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    async contributeContext(
      projectId: string,
      caseId: string,
      data: {
        category: string;
        title: string;
        content: string;
        rationale?: string;
      }
    ): Promise<HandoverContextContributionResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/context`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async assemblePackage(projectId: string, caseId: string, data?: {
      assembly_notes?: string;
      include_domains?: string[];
      exclude_knowledge_item_ids?: string[];
      exclude_relationship_ids?: string[];
    }): Promise<any> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/assemble`, {
        method: "POST",
        body: JSON.stringify(data || {}),
      });
    },
    async getVersions(projectId: string, caseId: string): Promise<HandoverPackageVersionSummary[]> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/versions`);
    },
    async getVersionSections(
      projectId: string,
      caseId: string,
      versionId: string,
      role?: string
    ): Promise<HandoverVersionSectionsResponse> {
      const q = role ? `?role=${encodeURIComponent(role)}` : "";
      return request(`/projects/${projectId}/handover/cases/${caseId}/versions/${versionId}/sections${q}`);
    },
    async draftSectionNarrative(
      projectId: string,
      caseId: string,
      data: {
        version_id: string;
        section_type: string;
        additional_context?: string;
      }
    ): Promise<{
      section_id: string;
      section_type: string;
      draft_content: string;
      content_summary?: string;
      findings_count: number;
    }> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/narrative/draft`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async editSectionContent(
      projectId: string,
      sectionId: string,
      data: {
        section_content?: string;
        content_summary?: string;
      }
    ): Promise<{
      id: string;
      version_id: string;
      section_type: string;
      section_title: string;
      section_content: string;
      content_summary?: string;
    }> {
      return request(`/projects/${projectId}/handover/sections/${sectionId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    async getVersionDetail(projectId: string, caseId: string, versionId: string): Promise<{
      version: any;
      sections: Array<{
        id: string;
        version_id: string;
        section_type: string;
        section_title: string;
        section_content: string;
        content_summary?: string;
        section_order: number;
        knowledge_item_count: number;
        relationship_count: number;
      }>;
      readiness?: {
        version_id: string;
        overall_score: number;
        overall_level: string;
        is_ready_for_signoff: boolean;
        blocker_count: number;
        warning_count: number;
        categories: Array<{
          category: string;
          score: number;
          level: string;
          findings_count: number;
          blockers_json: string[];
          warnings_json: string[];
        }>;
      };
      checklists?: Array<any>;
    }> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/versions/${versionId}`);
    },
    async assessReadiness(
      projectId: string,
      caseId: string,
      versionId: string,
      notes?: string,
    ): Promise<HandoverReadinessIntelligenceResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/readiness`, {
        method: "POST",
        body: JSON.stringify({ version_id: versionId, notes: notes || "Readiness assessment" }),
      });
    },
    async getReadiness(
      projectId: string,
      caseId: string,
      versionId: string,
    ): Promise<HandoverReadinessIntelligenceResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/readiness/${versionId}`);
    },
    async generateChecklists(
      projectId: string,
      caseId: string,
      versionId?: string,
    ): Promise<HandoverChecklistGroupDetail[]> {
      const q = versionId ? `?version_id=${versionId}` : "";
      return request(`/projects/${projectId}/handover/cases/${caseId}/checklists/generate${q}`, {
        method: "POST",
      });
    },
    async getChecklists(
      projectId: string,
      caseId: string,
    ): Promise<HandoverChecklistGroupDetail[]> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/checklists`);
    },
    async getChecklistWorkspace(
      projectId: string,
      caseId: string,
    ): Promise<HandoverChecklistWorkspaceResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/checklists/workspace`);
    },
    async createChecklistItem(
      projectId: string,
      caseId: string,
      checklistId: string,
      data: {
        item_text: string;
        description?: string;
        completion_criteria?: string;
        category?: string;
        blocking?: boolean;
        assigned_to_user_id?: string | null;
        due_date?: string | null;
        evidence_item_id?: string | null;
      },
    ): Promise<HandoverChecklistItemDetail> {
      return request(
        `/projects/${projectId}/handover/cases/${caseId}/checklists/${checklistId}/items`,
        {
          method: "POST",
          body: JSON.stringify(data),
        },
      );
    },
    async updateChecklistItem(
      projectId: string,
      itemId: string,
      data: {
        status?: string;
        notes?: string;
        description?: string;
        completion_criteria?: string;
        assigned_to_user_id?: string | null;
        clear_assignee?: boolean;
        due_date?: string | null;
        clear_due_date?: boolean;
        evidence_item_id?: string | null;
        clear_evidence?: boolean;
        blocking?: boolean;
        reopen_reason?: string;
        expected_version?: number;
      },
    ): Promise<HandoverChecklistItemDetail> {
      return request(`/projects/${projectId}/handover/checklists/items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    async reviewChecklistItem(
      projectId: string,
      itemId: string,
      data: {
        approved: boolean;
        review_notes?: string;
        expected_version?: number;
      },
    ): Promise<HandoverChecklistItemDetail> {
      return request(`/projects/${projectId}/handover/checklists/items/${itemId}/review`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async getResponsibilities(
      projectId: string,
      caseId: string,
    ): Promise<HandoverResponsibilityTransferDetail[]> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/responsibilities`);
    },
    async getResponsibilityWorkspace(
      projectId: string,
      caseId: string,
    ): Promise<HandoverResponsibilityWorkspaceResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/responsibilities/workspace`);
    },
    async createResponsibilities(
      projectId: string,
      caseId: string,
      transfers: Array<{
        title?: string;
        responsibility_description: string;
        knowledge_domain?: string;
        component_name?: string;
        priority?: string;
        ownership_certainty?: string;
        operational_context?: string;
        required_access?: string;
        effective_transfer_date?: string | null;
        current_owner_id?: string | null;
        proposed_successor_id?: string | null;
        transfer_notes?: string;
        related_entity_id?: string | null;
        related_knowledge_item_id?: string | null;
      }>,
    ): Promise<HandoverResponsibilityTransferDetail[]> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/responsibilities`, {
        method: "POST",
        body: JSON.stringify({ transfers }),
      });
    },
    async updateResponsibility(
      projectId: string,
      transferId: string,
      statusOrBody:
        | string
        | {
            title?: string;
            responsibility_description?: string;
            knowledge_domain?: string;
            component_name?: string;
            priority?: string;
            ownership_certainty?: string;
            operational_context?: string;
            required_access?: string;
            effective_transfer_date?: string | null;
            clear_effective_date?: boolean;
            proposed_successor_id?: string | null;
            clear_successor?: boolean;
            transfer_status?: string;
            transfer_notes?: string;
            blocker_reason?: string;
            expected_version?: number;
          },
      notes?: string,
    ): Promise<HandoverResponsibilityTransferDetail> {
      if (typeof statusOrBody === "string") {
        const q = notes
          ? `?status=${encodeURIComponent(statusOrBody)}&notes=${encodeURIComponent(notes)}`
          : `?status=${encodeURIComponent(statusOrBody)}`;
        return request(`/projects/${projectId}/handover/responsibilities/${transferId}${q}`, {
          method: "PATCH",
        });
      }
      return request(`/projects/${projectId}/handover/responsibilities/${transferId}`, {
        method: "PATCH",
        body: JSON.stringify(statusOrBody),
      });
    },
    async confirmResponsibilityOutgoing(
      projectId: string,
      transferId: string,
      data: { confirmation_notes?: string; expected_version?: number } = {},
    ): Promise<HandoverResponsibilityTransferDetail> {
      return request(
        `/projects/${projectId}/handover/responsibilities/${transferId}/confirm-outgoing`,
        {
          method: "POST",
          body: JSON.stringify(data),
        },
      );
    },
    async acknowledgeResponsibilitySuccessor(
      projectId: string,
      transferId: string,
      data: { acknowledgement_notes?: string; expected_version?: number } = {},
    ): Promise<HandoverResponsibilityTransferDetail> {
      return request(
        `/projects/${projectId}/handover/responsibilities/${transferId}/acknowledge`,
        {
          method: "POST",
          body: JSON.stringify(data),
        },
      );
    },
    async clarifyResponsibility(
      projectId: string,
      transferId: string,
      data: { notes: string; mode: "request" | "response"; expected_version?: number },
    ): Promise<HandoverResponsibilityTransferDetail> {
      return request(`/projects/${projectId}/handover/responsibilities/${transferId}/clarify`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async reopenResponsibility(
      projectId: string,
      transferId: string,
      data: { reason: string; expected_version?: number },
    ): Promise<HandoverResponsibilityTransferDetail> {
      return request(`/projects/${projectId}/handover/responsibilities/${transferId}/reopen`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async getSignoffs(projectId: string, caseId: string): Promise<HandoverSignoffRecord[]> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/signoffs`);
    },
    async getSignoffWorkspace(
      projectId: string,
      caseId: string,
      versionId?: string | null,
    ): Promise<HandoverSignoffWorkspaceResponse> {
      const q = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
      return request(`/projects/${projectId}/handover/cases/${caseId}/signoffs/workspace${q}`);
    },
    async submitSignoff(
      projectId: string,
      caseId: string,
      data: {
        version_id: string;
        signoff_type: string;
        decision: string;
        comments?: string;
        conditions?: string;
        affected_sections?: string[];
        expected_content_hash?: string | null;
        expected_case_version?: number;
      },
    ): Promise<HandoverSignoffRecord> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/signoffs`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async assignReviewer(
      projectId: string,
      caseId: string,
      data: {
        reviewer_user_id: string;
        reason?: string;
        expected_case_version?: number;
      },
    ): Promise<HandoverSignoffWorkspaceResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/signoffs/reviewer`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async reopenSignoffPhase(
      projectId: string,
      caseId: string,
      data: {
        signoff_type: string;
        reason: string;
        expected_case_version?: number;
      },
    ): Promise<HandoverSignoffWorkspaceResponse> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/signoffs/reopen`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async deliverPackage(
      projectId: string,
      caseId: string,
      data: {
        version_id: string;
        deliver_to_user_ids: string[];
        delivery_method?: string;
        message?: string;
        expires_in_days?: number;
        expected_content_hash?: string | null;
        expected_case_version?: number;
      },
    ): Promise<HandoverDeliveryRecord[]> {
      return request(`/projects/${projectId}/handover/cases/${caseId}/deliver`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async acknowledgeDelivery(
      projectId: string,
      deliveryId: string,
      data: {
        acknowledgement_notes?: string;
        confirmations?: Record<string, boolean>;
        expected_content_hash?: string | null;
      },
    ): Promise<HandoverAcknowledgementRecord> {
      return request(`/projects/${projectId}/handover/deliveries/${deliveryId}/acknowledge`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async clarifyDelivery(
      projectId: string,
      deliveryId: string,
      data: {
        notes: string;
        mode: "request" | "response";
      },
    ): Promise<HandoverDeliveryRecord> {
      return request(`/projects/${projectId}/handover/deliveries/${deliveryId}/clarify`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async exportMarkdown(
      projectId: string,
      caseId: string,
      opts?: { versionId?: string; role?: string }
    ): Promise<string> {
      const params = new URLSearchParams({ format: "markdown" });
      if (opts?.versionId) params.set("version_id", opts.versionId);
      if (opts?.role) params.set("role", opts.role);
      return request(`/projects/${projectId}/handover/cases/${caseId}/export?${params.toString()}`);
    },
    async exportJson(
      projectId: string,
      caseId: string,
      opts?: { versionId?: string; role?: string }
    ): Promise<Record<string, unknown>> {
      const params = new URLSearchParams({ format: "json" });
      if (opts?.versionId) params.set("version_id", opts.versionId);
      if (opts?.role) params.set("role", opts.role);
      return request(`/projects/${projectId}/handover/cases/${caseId}/export?${params.toString()}`);
    },
    async exportPdf(
      projectId: string,
      caseId: string,
      opts?: { versionId?: string; role?: string }
    ): Promise<Blob> {
      const params = new URLSearchParams({ format: "pdf" });
      if (opts?.versionId) params.set("version_id", opts.versionId);
      if (opts?.role) params.set("role", opts.role);
      return request(`/projects/${projectId}/handover/cases/${caseId}/export?${params.toString()}`);
    },
  },
  onboarding: {
    async getProgress(
      projectId: string,
      targetUserId?: string,
      opts?: { caseId?: string; versionId?: string }
    ): Promise<OnboardingProgressResponse> {
      const params = new URLSearchParams();
      if (targetUserId) params.set("target_user_id", targetUserId);
      if (opts?.caseId) params.set("case_id", opts.caseId);
      if (opts?.versionId) params.set("version_id", opts.versionId);
      const q = params.toString() ? `?${params.toString()}` : "";
      return request<OnboardingProgressResponse>(
        `/projects/${projectId}/handover/onboarding/progress${q}`
      );
    },
    async updateStep(
      projectId: string,
      stepId: string,
      isCompleted: boolean = true,
      opts?: { caseId?: string; versionId?: string }
    ): Promise<OnboardingStepProgressItem> {
      const params = new URLSearchParams();
      if (opts?.caseId) params.set("case_id", opts.caseId);
      if (opts?.versionId) params.set("version_id", opts.versionId);
      const q = params.toString() ? `?${params.toString()}` : "";
      return request<OnboardingStepProgressItem>(
        `/projects/${projectId}/handover/onboarding/progress/${encodeURIComponent(stepId)}${q}`,
        {
          method: "PUT",
          body: JSON.stringify({ is_completed: isCompleted }),
        }
      );
    },
    async deleteStep(
      projectId: string,
      stepId: string,
      opts?: { caseId?: string; versionId?: string }
    ): Promise<{ status: string; step_id: string }> {
      const params = new URLSearchParams();
      if (opts?.caseId) params.set("case_id", opts.caseId);
      if (opts?.versionId) params.set("version_id", opts.versionId);
      const q = params.toString() ? `?${params.toString()}` : "";
      return request<{ status: string; step_id: string }>(
        `/projects/${projectId}/handover/onboarding/progress/${encodeURIComponent(stepId)}${q}`,
        {
          method: "DELETE",
        }
      );
    },
  },
  assistant: {
    async listConversations(projectId: string): Promise<AssistantConversation[]> {
      return request<AssistantConversation[]>(`/projects/${projectId}/assistant/conversations`);
    },
    async createConversation(
      projectId: string,
      title?: string,
      metadata_json?: Record<string, unknown>
    ): Promise<AssistantConversation> {
      return request<AssistantConversation>(`/projects/${projectId}/assistant/conversations`, {
        method: "POST",
        body: JSON.stringify({
          title: title || "New Investigation",
          ...(metadata_json ? { metadata_json } : {}),
        }),
      });
    },
    async getConversation(projectId: string, conversationId: string): Promise<AssistantConversationDetail> {
      return request<AssistantConversationDetail>(`/projects/${projectId}/assistant/conversations/${conversationId}`);
    },
    async askQuestion(
      projectId: string,
      conversationId: string,
      data: {
        question: string;
        mode?: "hybrid" | "keyword" | "semantic";
        response_mode?: AssistantResponseMode;
        include_domains?: string[];
        max_citations?: number;
        handover_case_id?: string;
        package_version_id?: string;
        current_section?: string;
      }
    ): Promise<AssistantAnswerResponse> {
      return request<AssistantAnswerResponse>(
        `/projects/${projectId}/assistant/conversations/${conversationId}/messages`,
        {
          method: "POST",
          body: JSON.stringify({
            question: data.question,
            mode: data.mode || "hybrid",
            response_mode: data.response_mode || "standard",
            include_domains: data.include_domains,
            max_citations: data.max_citations || 8,
            ...(data.handover_case_id ? { handover_case_id: data.handover_case_id } : {}),
            ...(data.package_version_id ? { package_version_id: data.package_version_id } : {}),
            ...(data.current_section ? { current_section: data.current_section } : {}),
          }),
        }
      );
    },
    async sendMessage(
      projectId: string,
      conversationId: string,
      contentOrQuestion: string,
      options?: {
        mode?: "hybrid" | "keyword" | "semantic";
        response_mode?: AssistantResponseMode;
        include_domains?: string[];
        max_citations?: number;
        handover_case_id?: string;
        package_version_id?: string;
        current_section?: string;
      }
    ): Promise<AssistantAnswerResponse> {
      return this.askQuestion(projectId, conversationId, {
        question: contentOrQuestion,
        mode: options?.mode,
        response_mode: options?.response_mode,
        include_domains: options?.include_domains,
        max_citations: options?.max_citations,
        handover_case_id: options?.handover_case_id,
        package_version_id: options?.package_version_id,
        current_section: options?.current_section,
      });
    },
    async getMessages(projectId: string, conversationId: string): Promise<AssistantConversationDetail["messages"]> {
      const detail = await this.getConversation(projectId, conversationId);
      return detail.messages || [];
    },
    async deleteConversation(projectId: string, conversationId: string): Promise<void> {
      return request(`/projects/${projectId}/assistant/conversations/${conversationId}`, {
        method: "DELETE",
      });
    },
    async submitFeedback(
      projectId: string,
      messageId: string,
      data: {
        feedback_type: "helpful" | "unhelpful" | "incorrect_fact" | "missing_citation" | "unauthorized_source";
        comment?: string;
      }
    ): Promise<{ id: string; message_id: string; user_id: string; feedback_type: string; comment?: string }> {
      return request(`/projects/${projectId}/assistant/messages/${messageId}/feedback`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    async getDiagnostics(projectId: string, runId: string): Promise<unknown> {
      return request(`/projects/${projectId}/assistant/diagnostics/retrieval/${runId}`);
    },
      async startInvestigation(
      projectId: string,
      conversationId: string,
      data: {
        question: string;
        mode?: "hybrid" | "keyword" | "semantic";
        response_mode?: AssistantResponseMode;
        include_domains?: string[];
      }
    ): Promise<{
      investigation_id: string;
      conversation_id: string;
      status: string;
      events_url: string;
    }> {
      return request(
        `/projects/${projectId}/assistant/conversations/${conversationId}/investigations`,
        {
          method: "POST",
          body: JSON.stringify({
            question: data.question,
            mode: data.mode || "hybrid",
            response_mode: data.response_mode || "standard",
            include_domains: data.include_domains,
          }),
        }
      );
    },
    async getInvestigation(
      projectId: string,
      investigationId: string
    ): Promise<{
      investigation_id: string;
      status: string;
      answer_status: string;
      raw_answer: string;
      claims: Array<{ claim_text: string; citation_labels: string[] }>;
      conflicts: string[];
      uncertainty: string;
      missing_information: string[];
      suggested_followups: string[];
      response_mode: AssistantResponseMode;
      validated_citations: Array<{
        citation_label: string;
        source_title: string;
        source_provider: string;
        excerpt?: string;
      }>;
    }> {
      return request(`/projects/${projectId}/assistant/investigations/${investigationId}`);
    },
  },
  audit: {
    async listOrganisationEvents(orgId: string, limit: number = 50, offset: number = 0): Promise<{
      items: Array<{
        id: string;
        organisation_id: string;
        project_id?: string | null;
        user_id?: string | null;
        action: string;
        entity_type: string;
        entity_id?: string | null;
        outcome: string;
        created_at: string;
        actor_name?: string | null;
        details?: Record<string, unknown> | null;
      }>;
      total: number;
    }> {
      return request(`/organisations/${orgId}/audit-events?limit=${limit}&offset=${offset}`);
    },
  },
};
