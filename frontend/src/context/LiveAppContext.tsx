"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import { api, setStoredToken, setStoredUser, getStoredUser, ApiError } from "../lib/api";
import { createClient as createSupabaseClient } from "../lib/supabase/client";
import type {
  User,
  Organisation,
  Project,
  ProjectOverview,
  ProjectMember,
  ProjectSourceMapping,
  SourceConnection,
  EvidenceSummary,
  EvidenceDetail,
  EvidenceMetrics,
  KnowledgeFinding,
  KnowledgeSummaryTelemetry,
  VerificationSummaryData,
  VerificationCaseQueueItem,
  HandoverCaseItem,
  NotificationItem,
  ActiveSyncJob,
} from "../lib/types";

export interface ToastMessage {
  id: string;
  type: "success" | "info" | "warning" | "error";
  title: string;
  message: string;
}

interface LiveAppContextType {
  // Auth
  user: User | null;
  token: string | null;
  isLoadingAuth: boolean;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;

  // Organisations
  organisations: Organisation[];
  activeOrg: Organisation | null;
  setActiveOrg: (org: Organisation) => void;
  createOrganisation: (name: string, slug?: string) => Promise<Organisation>;

  // Projects
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
  createProject: (
    data: { name: string; slug?: string; description?: string; target_handover_date?: string },
    options?: { orgId?: string; newOrgName?: string }
  ) => Promise<Project>;
  isLoadingProjects: boolean;
  refreshProjects: () => Promise<void>;

  // Overview
  overview: ProjectOverview | null;
  isLoadingOverview: boolean;
  refreshOverview: () => Promise<void>;

  // Team Members
  members: ProjectMember[];
  isLoadingMembers: boolean;
  addMember: (data: { email?: string; user_id?: string; role_name?: string; transition_role?: string }) => Promise<void>;
  updateMember: (memberId: string, data: { role_name?: string; transition_role?: string }) => Promise<void>;
  refreshMembers: () => Promise<void>;

  // Sources
  sourceMappings: ProjectSourceMapping[];
  orgConnections: SourceConnection[];
  isLoadingSources: boolean;
  connectSource: (provider: "github" | "jira" | "slack", token: string, accountId: string) => Promise<SourceConnection>;
  createMapping: (data: { source_connection_id: string; external_resource_key: string; external_resource_name: string; external_resource_url?: string }) => Promise<ProjectSourceMapping>;
  triggerSync: (mappingId: string) => Promise<void>;
  refreshSources: () => Promise<void>;

  // Evidence
  evidenceList: EvidenceSummary[];
  evidenceMetrics: EvidenceMetrics | null;
  selectedEvidenceId: string | null;
  selectedEvidence: EvidenceDetail | null;
  isLoadingEvidence: boolean;
  isLoadingEvidenceDetail: boolean;
  evidenceFilter: { q: string; provider: string };
  setEvidenceFilter: React.Dispatch<React.SetStateAction<{ q: string; provider: string }>>;
  setSelectedEvidenceId: (id: string | null) => void;
  refreshEvidence: () => Promise<void>;
  uploadDocument: (
    file: File,
    title?: string,
    options?: { documentCategory?: string; documentSubtype?: string }
  ) => Promise<{ document_id: string; title: string }>;
  downloadEvidence: (evidenceId: string, filename?: string) => Promise<void>;

  // Downstream intelligence
  knowledgeSummary: KnowledgeSummaryTelemetry | null;
  findings: KnowledgeFinding[];
  isLoadingFindings: boolean;
  refreshFindings: () => Promise<void>;
  triggerReconstruction: () => Promise<void>;

  // Verification
  verificationSummary: VerificationSummaryData | null;
  verificationQueue: VerificationCaseQueueItem[];
  isLoadingVerification: boolean;
  refreshVerification: () => Promise<void>;
  approveVerificationCase: (caseId: string, notes?: string) => Promise<void>;
  rejectVerificationCase: (caseId: string, reason?: string) => Promise<void>;

  // Handover
  handoverCases: HandoverCaseItem[];
  isLoadingHandovers: boolean;
  refreshHandovers: () => Promise<void>;
  createHandoverCase: (data: {
    title: string;
    description?: string;
    departing_member_id?: string;
    successor_id?: string;
    metadata_json?: Record<string, unknown>;
  }) => Promise<Record<string, unknown>>;

  // UI state & modals
  isAuthModalOpen: boolean;
  setIsAuthModalOpen: (open: boolean) => void;
  authModalMode: "login" | "register";
  setAuthModalMode: (mode: "login" | "register") => void;
  openAuthModal: (mode?: "login" | "register") => void;
  closeAuthModal: () => void;
  isCreateOrgModalOpen: boolean;
  setIsCreateOrgModalOpen: (open: boolean) => void;
  isCreateProjectModalOpen: boolean;
  setIsCreateProjectModalOpen: (open: boolean) => void;
  isAddSourceModalOpen: boolean;
  setIsAddSourceModalOpen: (open: boolean) => void;
  initialSourceProvider: "github" | "jira" | "slack" | "docs" | "confluence" | "gdrive";
  setInitialSourceProvider: (provider: "github" | "jira" | "slack" | "docs" | "confluence" | "gdrive") => void;
  openConnectSourceModal: (provider?: "github" | "jira" | "slack" | "docs" | "confluence" | "gdrive") => void;
  isUploadModalOpen: boolean;
  setIsUploadModalOpen: (open: boolean) => void;
  isAddMemberModalOpen: boolean;
  setIsAddMemberModalOpen: (open: boolean) => void;
  isMobileSidebarOpen: boolean;
  setIsMobileSidebarOpen: (open: boolean) => void;

  // Persistent Notifications & Background Tasks
  notifications: NotificationItem[];
  unreadNotificationsCount: number;
  unreadNotificationCount?: number;
  activeJobs: ActiveSyncJob[];
  refreshNotifications: () => Promise<void>;
  refreshActiveJobs: () => Promise<void>;
  markNotificationRead: (id: string, isRead?: boolean) => Promise<void>;
  markAllNotificationsRead: () => Promise<void>;

  // Toasts
  toasts: ToastMessage[];
  addToast: (toast: Omit<ToastMessage, "id">) => void;
  dismissToast: (id: string) => void;
}

const LiveAppContext = createContext<LiveAppContextType | undefined>(undefined);

export function LiveAppProvider({ children }: { children: ReactNode }) {
  // Auth state
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);

  // Org & Project state
  const [organisations, setOrganisations] = useState<Organisation[]>([]);
  const [activeOrg, setActiveOrgInternal] = useState<Organisation | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProjectInternal] = useState<Project | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);

  // Overview state
  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const overviewRef = useRef<ProjectOverview | null>(null);
  overviewRef.current = overview;
  const [isLoadingOverview, setIsLoadingOverview] = useState(false);

  // Members state
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);

  // Sources state
  const [sourceMappings, setSourceMappings] = useState<ProjectSourceMapping[]>([]);
  const [orgConnections, setOrgConnections] = useState<SourceConnection[]>([]);
  const [isLoadingSources, setIsLoadingSources] = useState(false);

  // Evidence state
  const [evidenceList, setEvidenceList] = useState<EvidenceSummary[]>([]);
  const [evidenceMetrics, setEvidenceMetrics] = useState<EvidenceMetrics | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceDetail | null>(null);

  // Downstream intelligence states
  const [knowledgeSummary, setKnowledgeSummary] = useState<KnowledgeSummaryTelemetry | null>(null);
  const [findings, setFindings] = useState<KnowledgeFinding[]>([]);
  const [isLoadingFindings, setIsLoadingFindings] = useState(false);

  // Verification states
  const [verificationSummary, setVerificationSummary] = useState<VerificationSummaryData | null>(null);
  const [verificationQueue, setVerificationQueue] = useState<VerificationCaseQueueItem[]>([]);
  const [isLoadingVerification, setIsLoadingVerification] = useState(false);

  // Handover states
  const [handoverCases, setHandoverCases] = useState<HandoverCaseItem[]>([]);
  const [isLoadingHandovers, setIsLoadingHandovers] = useState(false);
  const [isLoadingEvidence, setIsLoadingEvidence] = useState(false);
  const [isLoadingEvidenceDetail, setIsLoadingEvidenceDetail] = useState(false);
  const [evidenceFilter, setEvidenceFilter] = useState<{ q: string; provider: string }>({
    q: "",
    provider: "all",
  });

  // Notifications & Active Background Jobs state
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadNotificationsCount, setUnreadNotificationsCount] = useState<number>(0);
  const [activeJobs, setActiveJobs] = useState<ActiveSyncJob[]>([]);
  const activeJobsRef = useRef<ActiveSyncJob[]>([]);
  activeJobsRef.current = activeJobs;

  // Organisation selector wrapper that persists user workspace preference
  const setActiveOrg = useCallback(
    (action: Organisation | null | ((prev: Organisation | null) => Organisation | null)) => {
      setActiveOrgInternal((prev) => {
        const next = typeof action === "function" ? action(prev) : action;
        if (next && typeof window !== "undefined") {
          localStorage.setItem("handover_active_org_id", next.id);
        } else if (!next && typeof window !== "undefined") {
          localStorage.removeItem("handover_active_org_id");
        }
        return next;
      });
    },
    []
  );

  // Project selector wrapper that resets stale project-specific caches
  const setActiveProject = useCallback(
    (action: Project | null | ((prev: Project | null) => Project | null)) => {
      setActiveProjectInternal((prev) => {
        const next = typeof action === "function" ? action(prev) : action;
        if (next && typeof window !== "undefined") {
          localStorage.setItem("handover_active_project_id", next.id);
        } else if (!next && typeof window !== "undefined") {
          localStorage.removeItem("handover_active_project_id");
        }
        if (prev?.id === next?.id) return prev;
        setOverview(null);
        setMembers([]);
        setEvidenceList([]);
        setSourceMappings([]);
        return next;
      });
    },
    []
  );

  // Modals & UI
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState<"login" | "register">("login");
  const openAuthModal = useCallback((mode: "login" | "register" = "login") => {
    setAuthModalMode(mode);
    if (typeof window !== "undefined") {
      window.location.href = mode === "login" ? "/login" : "/signup";
    }
  }, []);
  const closeAuthModal = useCallback(() => {
    setIsAuthModalOpen(false);
  }, []);

  const [isCreateOrgModalOpen, setIsCreateOrgModalOpen] = useState(false);
  const [isCreateProjectModalOpen, setIsCreateProjectModalOpen] = useState(false);
  const [isAddSourceModalOpen, setIsAddSourceModalOpen] = useState(false);
  const [initialSourceProvider, setInitialSourceProvider] = useState<"github" | "jira" | "slack" | "docs" | "confluence" | "gdrive">("github");
  const openConnectSourceModal = useCallback((prov: "github" | "jira" | "slack" | "docs" | "confluence" | "gdrive" = "github") => {
    setInitialSourceProvider(prov);
    setIsAddSourceModalOpen(true);
  }, []);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isAddMemberModalOpen, setIsAddMemberModalOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((toast: Omit<ToastMessage, "id">) => {
    const id = "toast_" + Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { ...toast, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Listen for global session expiration events dispatched by api.ts
  useEffect(() => {
    const handleSessionExpired = () => {
      setStoredToken(null);
      setToken(null);
      setUser(null);
      setActiveOrg(null);
      setActiveProject(null);
      setOrganisations([]);
      setProjects([]);
      setMembers([]);
      setEvidenceList([]);
      setOverview(null);
    };

    window.addEventListener("handover:session-expired", handleSessionExpired);
    return () => {
      window.removeEventListener("handover:session-expired", handleSessionExpired);
    };
  }, []);

  // Initialize auth from localStorage and verify with backend
  useEffect(() => {
    async function initAuth() {
      try {
        // First check if there's an active Supabase session waiting to be exchanged
        try {
          const supabase = createSupabaseClient();
          if (supabase) {
            const { data } = await supabase.auth.getSession();
            if (data?.session?.access_token) {
              try {
                const exchangeRes = await api.auth.exchangeSupabaseToken(data.session.access_token);
                setStoredToken(exchangeRes.access_token);
                setStoredUser(exchangeRes.user);
                setToken(exchangeRes.access_token);
                setUser(exchangeRes.user);
                setIsLoadingAuth(false);
                return;
              } catch (exchangeErr) {
                // Non-fatal: Supabase token exchange failed (e.g. backend offline or expired), fall back to standard session check
                console.warn("Supabase token exchange skipped:", exchangeErr);
              }
            }
          }
        } catch {
          // Supabase client error, proceed to standard check
        }

        const stored = typeof window !== "undefined" ? localStorage.getItem("handover_access_token") : null;
        const cachedUser = getStoredUser();

        // If we have cached token & user, hydrate instantly in 0ms so user sees authenticated state without flash
        if (stored && cachedUser) {
          setStoredToken(stored);
          setToken(stored);
          setUser(cachedUser);
          setIsLoadingAuth(false);

          // Silently verify or refresh session in the background
          try {
            const me = await api.auth.me();
            setUser(me);
            setStoredUser(me);
          } catch {
            try {
              const refreshed = await api.auth.refreshToken();
              setStoredToken(refreshed.access_token);
              setStoredUser(refreshed.user);
              setToken(refreshed.access_token);
              setUser(refreshed.user);
            } catch {
              setStoredToken(null);
              setStoredUser(null);
              setToken(null);
              setUser(null);
            }
          }
          return;
        }

        setIsLoadingAuth(true);
        if (stored) {
          setStoredToken(stored);
          setToken(stored);
          try {
            const me = await api.auth.me();
            setUser(me);
            setStoredUser(me);
          } catch {
            try {
              const refreshed = await api.auth.refreshToken();
              setStoredToken(refreshed.access_token);
              setStoredUser(refreshed.user);
              setToken(refreshed.access_token);
              setUser(refreshed.user);
            } catch {
              setStoredToken(null);
              setStoredUser(null);
              setToken(null);
              setUser(null);
            }
          }
        } else {
          // If no access token is stored, attempt silent refresh from HttpOnly cookie
          try {
            const refreshed = await api.auth.refreshToken();
            setStoredToken(refreshed.access_token);
            setStoredUser(refreshed.user);
            setToken(refreshed.access_token);
            setUser(refreshed.user);
          } catch {
            // No active session, user remains unauthenticated
          }
        }
      } catch {
        // Silent auth init
      } finally {
        setIsLoadingAuth(false);
      }
    }
    initAuth();

    // Listen for OAuth redirects and token updates
    let unsubscribeSupabase: (() => void) | undefined;
    try {
      const supabase = createSupabaseClient();
      if (supabase) {
        const { data: authListener } = supabase.auth.onAuthStateChange(
          async (event, session) => {
            if ((event === "SIGNED_IN" || event === "TOKEN_REFRESHED") && session?.access_token) {
              try {
                const exchangeRes = await api.auth.exchangeSupabaseToken(session.access_token);
                setStoredToken(exchangeRes.access_token);
                setStoredUser(exchangeRes.user);
                setToken(exchangeRes.access_token);
                setUser(exchangeRes.user);
                setIsLoadingAuth(false);
              } catch (err) {
                console.warn("Failed to exchange Supabase session on auth state change:", err);
              }
            } else if (event === "SIGNED_OUT") {
              setStoredToken(null);
              setStoredUser(null);
              setToken(null);
              setUser(null);
            }
          }
        );
        unsubscribeSupabase = () => {
          authListener?.subscription?.unsubscribe();
        };
      }
    } catch {
      // Ignore Supabase client load errors
    }

    return () => {
      if (unsubscribeSupabase) {
        unsubscribeSupabase();
      }
    };
  }, []);

  // Once authenticated, load organisations
  const refreshOrganisations = useCallback(async () => {
    if (!user) return;
    try {
      const orgs = await api.organisations.list();
      setOrganisations(orgs);
      if (orgs.length > 0) {
        const storedOrgId = typeof window !== "undefined" ? localStorage.getItem("handover_active_org_id") : null;
        const preferredOrg =
          (storedOrgId ? orgs.find((o) => o.id === storedOrgId) : null) ??
          orgs.find((o) => o.name.toLowerCase().includes("handover")) ??
          orgs[0] ??
          null;
        setActiveOrg((current) => (current ? (orgs.find((o) => o.id === current.id) ?? preferredOrg) : preferredOrg));
      } else {
        setActiveOrg(null);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) return;
      console.error("Error loading organisations:", err);
    }
  }, [user, setActiveOrg]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      if (user) {
        await refreshOrganisations();
      } else {
        setOrganisations([]);
        setActiveOrg(null);
        setProjects([]);
        setActiveProject(null);
      }
    });
    return () => {
      active = false;
    };
  }, [user, refreshOrganisations, setActiveOrg, setActiveProject]);

  // Load projects for active organization
  const refreshProjects = useCallback(async () => {
    if (!user || !activeOrg) {
      setProjects([]);
      setActiveProject(null);
      return;
    }
    setIsLoadingProjects(true);
    try {
      const projs = await api.projects.list(activeOrg.id);
      setProjects(projs);
      if (projs.length > 0) {
        const storedProjId = typeof window !== "undefined" ? localStorage.getItem("handover_active_project_id") : null;
        const preferredProj =
          (storedProjId ? projs.find((p) => p.id === storedProjId) : null) ?? projs[0] ?? null;
        setActiveProject((current) => (current ? (projs.find((p) => p.id === current.id) ?? preferredProj) : preferredProj));
      } else {
        setActiveProject(null);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) return;
      console.error("Error loading projects:", err);
      addToast({
        type: "error",
        title: "Failed to load projects",
        message: err instanceof Error ? err.message : "Could not retrieve projects",
      });
    } finally {
      setIsLoadingProjects(false);
    }
  }, [user, activeOrg, addToast, setActiveProject]);

  useEffect(() => {
    if (!user || !activeOrg) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (active) {
        await refreshProjects();
      }
    });
    return () => {
      active = false;
    };
  }, [activeOrg, refreshProjects]);

  // Synchronize active project from URL pathname whenever navigating to /projects/:id
  useEffect(() => {
    if (!pathname) return;
    const match = pathname.match(/^\/projects\/([a-zA-Z0-9_-]+)/);
    if (!match || !match[1] || match[1] === "new") return;
    const urlProjectId = match[1];

    if (activeProject?.id === urlProjectId) return;

    const matchedProject = projects.find(
      (p) => p.id === urlProjectId || p.slug === urlProjectId
    );

    if (matchedProject) {
      setActiveProject(matchedProject);
    } else {
      let cancelled = false;
      api.projects
        .get(urlProjectId)
        .then((proj) => {
          if (!cancelled && proj) {
            setActiveProject(proj);
            if (proj.organisation_id && activeOrg?.id !== proj.organisation_id) {
              const org = organisations.find((o) => o.id === proj.organisation_id);
              if (org) setActiveOrg(org);
            }
          }
        })
        .catch(() => {
          // Ignore invalid project ID in URL
        });
      return () => {
        cancelled = true;
      };
    }
  }, [pathname, projects, activeProject?.id, organisations, activeOrg?.id, setActiveProject, setActiveOrg]);

  // Load project overview
  const refreshOverview = useCallback(async () => {
    if (!user || !activeProject) {
      setOverview(null);
      return;
    }
    const currentProjectId = activeProject.id;
    setIsLoadingOverview(true);
    try {
      const ov = await api.projects.getOverview(currentProjectId);
      setActiveProjectInternal((curr) => {
        if (curr?.id === currentProjectId) {
          setOverview(ov);
        }
        return curr;
      });
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) return;
      console.error("Error loading project overview:", err);
    } finally {
      setIsLoadingOverview(false);
    }
  }, [user, activeProject]);

  // Load project members
  const refreshMembers = useCallback(async () => {
    if (!user || !activeProject) {
      setMembers([]);
      return;
    }
    const currentProjectId = activeProject.id;
    setIsLoadingMembers(true);
    try {
      const [membersRes, transRes] = await Promise.allSettled([
        api.members.list(currentProjectId),
        api.projects.getTransition(currentProjectId),
      ]);
      const rawMembers = membersRes.status === "fulfilled" ? membersRes.value : [];
      const transitionData = transRes.status === "fulfilled"
        ? (transRes.value as { departing_user?: { id?: string }; successor_user?: { id?: string } } | null)
        : null;

      const currentOverview = overviewRef.current && overviewRef.current.project_id === currentProjectId ? overviewRef.current : null;
      const departingId = transitionData?.departing_user?.id || currentOverview?.departing_member?.id;
      const successorId = transitionData?.successor_user?.id || currentOverview?.successor?.id;

      const annotated = rawMembers.map((mem) => {
        let tRole: "departing_owner" | "incoming_assignee" | "reviewer" | null = null;
        if (mem.user_id === departingId) {
          tRole = "departing_owner";
        } else if (mem.user_id === successorId) {
          tRole = "incoming_assignee";
        } else if (mem.role_name === "reviewer") {
          tRole = "reviewer";
        }
        return {
          ...mem,
          transition_role: tRole,
        };
      });

      setActiveProjectInternal((curr) => {
        if (curr?.id === currentProjectId) {
          setMembers(annotated);
        }
        return curr;
      });
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) return;
      console.error("Error loading project members:", err);
    } finally {
      setIsLoadingMembers(false);
    }
  }, [user?.id, activeProject?.id]);

  // Load project sources & org connections
  const refreshSources = useCallback(async () => {
    if (!user || !activeProject || !activeOrg) {
      setSourceMappings([]);
      setOrgConnections([]);
      return;
    }
    setIsLoadingSources(true);
    try {
      const [mappingsRes, connsRes] = await Promise.allSettled([
        api.sources.listProjectMappings(activeProject.id),
        api.sources.listOrgConnections(activeOrg.id),
      ]);
      if (mappingsRes.status === "fulfilled") {
        setSourceMappings(mappingsRes.value);
      }
      if (connsRes.status === "fulfilled") {
        setOrgConnections(connsRes.value);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) return;
      console.error("Error loading sources:", err);
    } finally {
      setIsLoadingSources(false);
    }
  }, [user, activeProject, activeOrg]);

  // Load evidence list and metrics
  const isFetchingEvidenceRef = useRef(false);
  const refreshEvidence = useCallback(async () => {
    if (!user || !activeProject) {
      setEvidenceList([]);
      setEvidenceMetrics(null);
      return;
    }
    if (isFetchingEvidenceRef.current) return;
    isFetchingEvidenceRef.current = true;
    const currentProjectId = activeProject.id;
    setIsLoadingEvidence(true);
    try {
      const [itemsRes, metricsRes] = await Promise.allSettled([
        api.evidence.list(currentProjectId, {
          limit: 100,
        }),
        api.evidence.getMetrics(currentProjectId),
      ]);
      const items = itemsRes.status === "fulfilled" ? itemsRes.value : [];
      const metrics = metricsRes.status === "fulfilled" ? metricsRes.value : null;
      setEvidenceList(items);
      setEvidenceMetrics(metrics);
      if (items.length > 0 && items[0]) {
        const firstId = items[0].id;
        setSelectedEvidenceId((prev) => {
          if (!prev || !items.some((it) => it.id === prev)) {
            return firstId;
          }
          return prev;
        });
      } else {
        setSelectedEvidenceId(null);
        setSelectedEvidence(null);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) return;
      console.error("Error loading evidence:", err);
    } finally {
      setIsLoadingEvidence(false);
      isFetchingEvidenceRef.current = false;
    }
  }, [user?.id, activeProject?.id]);

  // Load evidence detail when selectedEvidenceId changes
  useEffect(() => {
    async function loadDetail() {
      if (!user || !selectedEvidenceId) {
        setSelectedEvidence(null);
        return;
      }
      setIsLoadingEvidenceDetail(true);
      try {
        const detail = await api.evidence.getDetail(selectedEvidenceId);
        setSelectedEvidence(detail);
      } catch (err: unknown) {
        if (err instanceof ApiError && err.status === 401) return;
        console.error("Error loading evidence detail:", err);
        setSelectedEvidence(null);
      } finally {
        setIsLoadingEvidenceDetail(false);
      }
    }
    loadDetail();
  }, [user?.id, selectedEvidenceId]);

  // Downstream Intelligence Handlers
  const refreshFindings = useCallback(async () => {
    if (!user || !activeProject) {
      setFindings([]);
      setKnowledgeSummary(null);
      return;
    }
    setIsLoadingFindings(true);
    try {
      const [sum, list] = await Promise.allSettled([
        api.knowledgeIntelligence.getSummary(activeProject.id),
        api.knowledgeIntelligence.listFindings(activeProject.id, undefined, 100, 0),
      ]);
      if (sum.status === "fulfilled") setKnowledgeSummary(sum.value as unknown as KnowledgeSummaryTelemetry);
      if (list.status === "fulfilled") {
        let allItems = (list.value.items || []) as unknown as KnowledgeFinding[];
        const total = list.value.total || 0;
        if (total > 100) {
          const pagesNeeded = Math.ceil(total / 100);
          const pagePromises = [];
          for (let p = 1; p < pagesNeeded; p++) {
            pagePromises.push(api.knowledgeIntelligence.listFindings(activeProject.id, undefined, 100, p * 100));
          }
          const pageResults = await Promise.allSettled(pagePromises);
          for (const res of pageResults) {
            if (res.status === "fulfilled" && res.value.items) {
              allItems = allItems.concat(res.value.items as unknown as KnowledgeFinding[]);
            }
          }
        }
        setFindings(allItems);
      }
    } catch (err) {
      console.error("Error loading findings:", err);
    } finally {
      setIsLoadingFindings(false);
    }
  }, [user?.id, activeProject?.id]);

  const triggerReconstruction = useCallback(async () => {
    if (!activeProject) return;
    try {
      setIsLoadingFindings(true);
      await api.knowledgeIntelligence.triggerExtraction(activeProject.id);
      addToast({
        type: "success",
        title: "AI Knowledge Reconstruction Started",
        message: "Ollama Qwen3 8B is reconstructing project knowledge from all gathered sources without timeout.",
      });
      await refreshFindings();
      await refreshOverview();

      // Poll periodically to stream in new findings as Ollama generates them
      let pollCount = 0;
      const pollInterval = setInterval(async () => {
        pollCount += 1;
        await refreshFindings();
        if (pollCount >= 12) {
          clearInterval(pollInterval);
        }
      }, 5000);
    } catch (err: unknown) {
      addToast({
        type: "error",
        title: "Reconstruction Failed",
        message: err instanceof Error ? err.message : "Failed to trigger knowledge extraction",
      });
    } finally {
      setIsLoadingFindings(false);
    }
  }, [activeProject, refreshFindings, refreshOverview, addToast]);

  const refreshVerification = useCallback(async () => {
    if (!user || !activeProject) {
      setVerificationQueue([]);
      setVerificationSummary(null);
      return;
    }
    setIsLoadingVerification(true);
    try {
      const [sum, q] = await Promise.allSettled([
        api.verification.getSummary(activeProject.id),
        api.verification.getQueue(activeProject.id),
      ]);
      if (sum.status === "fulfilled") setVerificationSummary(sum.value as unknown as VerificationSummaryData);
      if (q.status === "fulfilled") setVerificationQueue((q.value.items || []) as unknown as VerificationCaseQueueItem[]);
    } catch (err) {
      console.error("Error loading verification data:", err);
    } finally {
      setIsLoadingVerification(false);
    }
  }, [user?.id, activeProject?.id]);

  const approveVerificationCase = useCallback(async (caseId: string, notes?: string) => {
    if (!activeProject) return;
    try {
      const targetCase = verificationQueue.find((c) => c.id === caseId);
      const expectedVersion = (targetCase?.version as number) || 1;
      await api.verification.approveCase(activeProject.id, caseId, expectedVersion, notes);
      addToast({
        type: "success",
        title: "Finding Verified",
        message: "Statement verified and promoted to verified knowledge.",
      });
      await refreshVerification();
      await refreshFindings();
    } catch (err: unknown) {
      addToast({
        type: "error",
        title: "Approval Failed",
        message: err instanceof Error ? err.message : "Failed to approve verification case",
      });
    }
  }, [activeProject, verificationQueue, refreshVerification, refreshFindings, addToast]);

  const rejectVerificationCase = useCallback(async (caseId: string, reason?: string) => {
    if (!activeProject) return;
    try {
      const targetCase = verificationQueue.find((c) => c.id === caseId);
      const expectedVersion = (targetCase?.version as number) || 1;
      await api.verification.rejectCase(activeProject.id, caseId, expectedVersion, reason || "Rejected by reviewer");
      addToast({
        type: "info",
        title: "Finding Rejected",
        message: "Candidate finding was marked as rejected.",
      });
      await refreshVerification();
    } catch (err: unknown) {
      addToast({
        type: "error",
        title: "Rejection Failed",
        message: err instanceof Error ? err.message : "Failed to reject verification case",
      });
    }
  }, [activeProject, verificationQueue, refreshVerification, addToast]);

  const refreshHandovers = useCallback(async () => {
    if (!user || !activeProject) {
      setHandoverCases([]);
      return;
    }
    setIsLoadingHandovers(true);
    try {
      const res = await api.handover.listCases(activeProject.id);
      setHandoverCases((res.items || []) as unknown as HandoverCaseItem[]);
    } catch (err) {
      console.error("Error loading handover cases:", err);
    } finally {
      setIsLoadingHandovers(false);
    }
  }, [user?.id, activeProject?.id]);

  const createHandoverCase = useCallback(async (data: {
    title: string;
    description?: string;
    departing_member_id?: string;
    successor_id?: string;
    metadata_json?: Record<string, unknown>;
  }) => {
    if (!activeProject || !user) throw new Error("No active project or authenticated user");
    const res = await api.handover.createCase(activeProject.id, {
      ...data,
      departing_member_id: data.departing_member_id || user.id,
    });
    addToast({
      type: "success",
      title: "Handover Case Created",
      message: `Handover ${res.title} created successfully.`,
    });
    await refreshHandovers();
    return res;
  }, [activeProject, user, refreshHandovers, addToast]);

  // Notifications and Active Background Jobs
  const refreshNotifications = useCallback(async () => {
    if (!user) return;
    try {
      const res = await api.notifications.list(activeProject?.id);
      setNotifications(res.items as NotificationItem[]);
      setUnreadNotificationsCount(res.unread_count);
    } catch {
      // ignore
    }
  }, [user, activeProject?.id]);

  const refreshActiveJobs = useCallback(async () => {
    if (!user || !activeProject) {
      setActiveJobs([]);
      return;
    }
    try {
      const jobs = await api.notifications.listActiveJobs(activeProject.id);
      const prevJobs = activeJobsRef.current;
      setActiveJobs(jobs as ActiveSyncJob[]);

      // Check if any job completed
      if (prevJobs.length > 0 && jobs.length === 0) {
        void refreshEvidence();
        void refreshSources();
        void refreshOverview();
        void refreshNotifications();
        addToast({
          type: "success",
          title: "Background Task Finished",
          message: "All background sync and extraction jobs have completed.",
        });
      } else if (prevJobs.length > jobs.length) {
        void refreshEvidence();
        void refreshSources();
        void refreshNotifications();
      }
    } catch {
      // ignore
    }
  }, [user, activeProject, refreshEvidence, refreshSources, refreshOverview, refreshNotifications, addToast]);

  const markNotificationRead = useCallback(async (id: string, isRead: boolean = true) => {
    try {
      await api.notifications.markRead(id, isRead);
      setNotifications((prev) =>
        prev.map((n) =>
          n.id === id ? { ...n, is_read: isRead, read_at: isRead ? new Date().toISOString() : null } : n
        )
      );
      setUnreadNotificationsCount((prev) =>
        isRead ? Math.max(0, prev - 1) : prev + 1
      );
    } catch (err: unknown) {
      console.error("Failed to mark notification read", err);
    }
  }, []);

  const markAllNotificationsRead = useCallback(async () => {
    try {
      await api.notifications.markAllRead();
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      setUnreadNotificationsCount(0);
    } catch (err: unknown) {
      console.error("Failed to mark all notifications read", err);
    }
  }, []);

  // Poll for background sync jobs & notifications
  useEffect(() => {
    if (!user || !activeProject) return;

    void refreshNotifications();
    void refreshActiveJobs();

    const intervalTime = activeJobs.length > 0 ? 3000 : 7000;
    const timer = setInterval(() => {
      void refreshActiveJobs();
      void refreshNotifications();
    }, intervalTime);

    return () => clearInterval(timer);
  }, [user, activeProject?.id, activeJobs.length, refreshActiveJobs, refreshNotifications]);


  // Trigger data refreshes when active project changes
  const activeProjectId = activeProject?.id;
  const currentUserId = user?.id;
  const lastLoadedProjectIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!currentUserId || !activeProjectId) {
      lastLoadedProjectIdRef.current = null;
      return;
    }
    if (lastLoadedProjectIdRef.current === activeProjectId) {
      return;
    }
    lastLoadedProjectIdRef.current = activeProjectId;

    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      void refreshOverview();
      void refreshMembers();
      void refreshSources();
      void refreshEvidence();
      void refreshFindings();
      void refreshVerification();
      void refreshHandovers();
    });
    return () => {
      active = false;
    };
  }, [
    currentUserId,
    activeProjectId,
    refreshOverview,
    refreshMembers,
    refreshSources,
    refreshEvidence,
    refreshFindings,
    refreshVerification,
    refreshHandovers,
  ]);

  // Auth actions
  const login = async (email: string, password: string) => {
    const res = await api.auth.login({ email, password });
    setStoredToken(res.access_token);
    setStoredUser(res.user);
    setToken(res.access_token);
    setUser(res.user);
    addToast({
      type: "success",
      title: "Authenticated",
      message: `Signed in as ${res.user.email}`,
    });
  };

  const loginWithGoogle = async () => {
    const supabase = createSupabaseClient();
    if (!supabase) {
      throw new Error("Supabase Auth is not configured. Please check environment variables.");
    }
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const redirectTo = `${origin}/auth/callback`;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo,
        queryParams: {
          access_type: "offline",
          prompt: "consent",
        },
      },
    });
    if (error) {
      throw error;
    }
  };

  const register = async (email: string, password: string, fullName: string) => {
    await api.auth.register({ email, password, full_name: fullName });
    // After registration, log in
    await login(email, password);
    addToast({
      type: "success",
      title: "Account Created",
      message: "Welcome to The Handover!",
    });
  };

  const logout = async () => {
    try {
      await api.auth.logout();
    } catch {
      // ignore
    }
    try {
      const supabase = createSupabaseClient();
      if (supabase) {
        await supabase.auth.signOut();
      }
    } catch {
      // ignore
    }
    setStoredToken(null);
    setStoredUser(null);
    setToken(null);
    setUser(null);
    setActiveOrg(null);
    setActiveProject(null);
    setOrganisations([]);
    setProjects([]);
    setMembers([]);
    setEvidenceList([]);
    setOverview(null);
    addToast({
      type: "info",
      title: "Signed Out",
      message: "You have been logged out.",
    });
  };

  // Org & Project actions
  const createOrganisation = async (name: string, slug?: string) => {
    const org = await api.organisations.create({ name, slug });
    await refreshOrganisations();
    setActiveOrg(org);
    addToast({
      type: "success",
      title: "Organisation Created",
      message: `Organisation ${org.name} is ready`,
    });
    return org;
  };

  const createProject = async (
    data: { name: string; slug?: string; description?: string; target_handover_date?: string },
    options?: { orgId?: string; newOrgName?: string }
  ) => {
    let targetOrg: Organisation | null = activeOrg;

    if (options?.newOrgName && options.newOrgName.trim()) {
      targetOrg = await createOrganisation(options.newOrgName.trim());
    } else if (options?.orgId) {
      targetOrg = organisations.find((o) => o.id === options.orgId) ?? activeOrg;
    }

    if (!targetOrg && organisations.length > 0 && organisations[0]) {
      targetOrg = organisations[0];
      setActiveOrg(targetOrg);
    }

    if (!targetOrg) {
      throw new Error("Please specify or create an Organisation workspace first.");
    }

    const proj = await api.projects.create(targetOrg.id, data);
    await refreshProjects();
    setActiveProject(proj);
    setIsCreateProjectModalOpen(false);
    addToast({
      type: "success",
      title: "Project Workspace Created",
      message: `Project ${proj.name} is now active in ${targetOrg.name}`,
    });
    return proj;
  };

  // Member actions
  const addMember = async (data: { email?: string; user_id?: string; role_name?: string; transition_role?: string }) => {
    if (!activeProject) throw new Error("No active project");
    await api.members.add(activeProject.id, data);
    await refreshMembers();
    setIsAddMemberModalOpen(false);
    addToast({
      type: "success",
      title: "Member Added",
      message: "Team member joined the project workspace",
    });
  };

  const updateMember = async (memberId: string, data: { role_name?: string; transition_role?: string }) => {
    if (!activeProject) throw new Error("No active project");
    await api.members.update(activeProject.id, memberId, data);
    await refreshMembers();
    addToast({
      type: "success",
      title: "Role Updated",
      message: "Participant role updated successfully",
    });
  };

  // Source actions
  const connectSource = async (provider: "github" | "jira" | "slack", token: string, accountId: string) => {
    if (!activeOrg) throw new Error("No active organisation");
    const conn = await api.sources.connectSource(activeOrg.id, {
      provider,
      access_token: token,
      account_identifier: accountId,
    });
    await refreshSources();
    addToast({
      type: "success",
      title: "Source Connected",
      message: `Connected ${provider.toUpperCase()} account (${accountId})`,
    });
    return conn;
  };

  const createMapping = async (data: { source_connection_id: string; external_resource_key: string; external_resource_name: string; external_resource_url?: string }) => {
    if (!activeProject) throw new Error("No active project");
    const mapping = await api.sources.createProjectMapping(activeProject.id, data);
    await refreshSources();
    setIsAddSourceModalOpen(false);
    addToast({
      type: "success",
      title: "Resource Mapped",
      message: `Mapped ${mapping.external_resource_name} to project`,
    });
    return mapping;
  };

  const triggerSync = async (mappingId: string) => {
    if (!activeProject) return;
    try {
      const res = await api.sources.triggerSync(activeProject.id, mappingId);
      addToast({
        type: "info",
        title: "Sync Started",
        message: res.message || "Background sync job submitted",
      });
      await refreshSources();
      await refreshEvidence();
      await refreshOverview();
    } catch (err: unknown) {
      addToast({
        type: "error",
        title: "Sync Failed",
        message: err instanceof Error ? err.message : "Failed to trigger sync",
      });
    }
  };

  // Evidence actions
  const uploadDocument = async (
    file: File,
    title?: string,
    options?: { documentCategory?: string; documentSubtype?: string }
  ) => {
    if (!activeProject) throw new Error("No active project");
    const res = await api.evidence.upload(activeProject.id, file, {
      title: title || file.name,
      document_category: options?.documentCategory,
      document_subtype: options?.documentSubtype,
      custom_title: title,
    });
    await refreshEvidence();
    await refreshOverview();
    void refreshActiveJobs();
    void refreshNotifications();
    setIsUploadModalOpen(false);
    addToast({
      type: "success",
      title: "Document Ingested",
      message: `${file.name} uploaded and queued for processing`,
    });
    return res;
  };

  const downloadEvidence = async (evidenceId: string, filename?: string) => {
    try {
      const blob = await api.evidence.download(evidenceId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `evidence-${evidenceId.slice(0, 8)}.bin`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      addToast({
        type: "success",
        title: "Download Complete",
        message: `Decrypted ${filename || "evidence file"} successfully`,
      });
    } catch (err: unknown) {
      addToast({
        type: "error",
        title: "Download Failed",
        message: err instanceof Error ? err.message : "Could not download decrypted evidence",
      });
    }
  };

  const value: LiveAppContextType = {
    user,
    token,
    isLoadingAuth,
    setUser,
    setToken,
    login,
    loginWithGoogle,
    register,
    logout,
    organisations,
    activeOrg,
    setActiveOrg,
    createOrganisation,
    projects,
    activeProject,
    setActiveProject,
    createProject,
    isLoadingProjects,
    refreshProjects,
    overview,
    isLoadingOverview,
    refreshOverview,
    members,
    isLoadingMembers,
    addMember,
    updateMember,
    refreshMembers,
    sourceMappings,
    orgConnections,
    isLoadingSources,
    connectSource,
    createMapping,
    triggerSync,
    refreshSources,
    evidenceList,
    evidenceMetrics,
    selectedEvidenceId,
    selectedEvidence,
    isLoadingEvidence,
    isLoadingEvidenceDetail,
    evidenceFilter,
    setEvidenceFilter,
    setSelectedEvidenceId,
    refreshEvidence,
    uploadDocument,
    downloadEvidence,
    knowledgeSummary,
    findings,
    isLoadingFindings,
    refreshFindings,
    triggerReconstruction,
    verificationSummary,
    verificationQueue,
    isLoadingVerification,
    refreshVerification,
    approveVerificationCase,
    rejectVerificationCase,
    handoverCases,
    isLoadingHandovers,
    refreshHandovers,
    createHandoverCase,
    isAuthModalOpen,
    setIsAuthModalOpen,
    authModalMode,
    setAuthModalMode,
    openAuthModal,
    closeAuthModal,
    isCreateOrgModalOpen,
    setIsCreateOrgModalOpen,
    isCreateProjectModalOpen,
    setIsCreateProjectModalOpen,
    isAddSourceModalOpen,
    setIsAddSourceModalOpen,
    initialSourceProvider,
    setInitialSourceProvider,
    openConnectSourceModal,
    isUploadModalOpen,
    setIsUploadModalOpen,
    isAddMemberModalOpen,
    setIsAddMemberModalOpen,
    isMobileSidebarOpen,
    setIsMobileSidebarOpen,
    toasts,
    addToast,
    dismissToast,
    notifications,
    unreadNotificationsCount,
    unreadNotificationCount: unreadNotificationsCount,
    activeJobs,
    refreshNotifications,
    refreshActiveJobs,
    markNotificationRead,
    markAllNotificationsRead,
  };

  return (
    <LiveAppContext.Provider value={value}>
      {children}
    </LiveAppContext.Provider>
  );
}

export function useLiveApp() {
  const context = useContext(LiveAppContext);
  if (!context) {
    throw new Error("useLiveApp must be used within a LiveAppProvider");
  }
  return context;
}
