"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  Bot,
  Send,
  Plus,
  Trash2,
  Sparkles,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  AlertCircle,
  FileText,
  GitCommit,
  CheckCircle2,
  ThumbsUp,
  ThumbsDown,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  ChevronLeft,
  Database,
  Layers,
  Search,
  User,
  Clock,
  BookOpen,
  Brain,
  Table,
  Copy,
  CheckCheck,
  X,
  Cpu,
  Users,
  CheckSquare,
  Bell,
  Folder,
} from "lucide-react";
import Link from "next/link";
import { api } from "../../lib/api";
import { useLiveApp } from "../../context/LiveAppContext";
import { ListSkeleton } from "../loading";
import { AssistantThinking3D } from "./AssistantThinking3D";
import type {
  AssistantConversation,
  AssistantMessage,
  AssistantAnswerStatus,
  AssistantResponseMode,
} from "../../lib/types";

// Quick action questions matching general project exploration
const QUICK_QUESTIONS = [
  {
    title: "Project Overview & Goals",
    question: "What is the core purpose, mission, and current scope of this project?",
    category: "Overview",
    icon: BookOpen,
  },
  {
    title: "Architecture & Tech Stack",
    question: "What is the overall architecture, technology stack, and backend design?",
    category: "Architecture",
    icon: Layers,
  },
  {
    title: "Key Decisions & Rationale",
    question: "What are the key technical and architectural decisions made in this project and why?",
    category: "Decisions",
    icon: FileText,
  },
  {
    title: "Ownership & Responsibilities",
    question: "Who is responsible for the key modules and who are the primary points of contact?",
    category: "Ownership",
    icon: Users,
  },
  {
    title: "Tasks & Progress Status",
    question: "What work has been completed so far and what remains in progress?",
    category: "Tasks",
    icon: CheckSquare,
  },
  {
    title: "Blockers & Known Risks",
    question: "What are the main blockers, technical risks, or critical concerns identified?",
    category: "Risks",
    icon: ShieldAlert,
  },
];

// Domains mapping
const DOMAINS_LIST = [
  { id: "all", label: "All Knowledge Domains" },
  { id: "decisions_rationale", label: "Decisions & Rationale" },
  { id: "technical_architecture", label: "Technical Architecture" },
  { id: "work_progress", label: "Work Progress & Tasks" },
  { id: "responsibilities_ownership", label: "Ownership & Roles" },
  { id: "dependencies_relationships", label: "Dependencies" },
  { id: "bugs_blockers_risks", label: "Risks, Blockers & Bugs" },
  { id: "operational_historical", label: "Operations & Procedures" },
  { id: "project_overview_context", label: "Project Context" },
];

export function AssistantWorkspaceView() {
  const { activeProject, user, addToast } = useLiveApp();

  // State
  const [conversations, setConversations] = useState<AssistantConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [loadingConversations, setLoadingConversations] = useState<boolean>(true);
  const [loadingMessages, setLoadingMessages] = useState<boolean>(false);
  const [asking, setAsking] = useState<boolean>(false);
  const [liveInvestigationStage, setLiveInvestigationStage] = useState<string | null>(null);
  const [liveInvestigationEvents, setLiveInvestigationEvents] = useState<string[]>([]);
  const [liveStreamingAnswer, setLiveStreamingAnswer] = useState<string>("");

  // Floating side panel states (Both collapsible independently)
  const [leftPanelOpen, setLeftPanelOpen] = useState<boolean>(true);
  const [rightPanelOpen, setRightPanelOpen] = useState<boolean>(true);

  // Form input & composer options
  const [inputValue, setInputValue] = useState<string>("");
  const [selectedDomain, setSelectedDomain] = useState<string>("all");
  const [retrievalMode, setRetrievalMode] = useState<"hybrid" | "keyword" | "semantic">("hybrid");
  const [responseMode, setResponseMode] = useState<AssistantResponseMode>("standard");
  const [showSettingsPopover, setShowSettingsPopover] = useState<boolean>(false);

  // Interaction
  const [activeCitationLabel, setActiveCitationLabel] = useState<string | null>(null);
  const [evidenceFilterTab, setEvidenceFilterTab] = useState<string>("all");
  const [expandedClaims, setExpandedClaims] = useState<Record<string, boolean>>({});
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, "helpful" | "unhelpful">>({});
  const [searchThreadQuery, setSearchThreadQuery] = useState<string>("");
  const [copiedExtractId, setCopiedExtractId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const citationRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close popover when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setShowSettingsPopover(false);
      }
    }
    if (showSettingsPopover) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showSettingsPopover]);

  // Auto-scroll messages
  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, asking]);

  // Load conversations
  const loadConversations = useCallback(
    async (selectFirst = false) => {
      if (!activeProject?.id) return;
      setLoadingConversations(true);
      try {
        const list = await api.assistant.listConversations(activeProject.id).catch(() => []);
        setConversations(list || []);

        if (list && list.length > 0) {
          if (selectFirst || !activeConversationId || !list.some((c) => c.id === activeConversationId)) {
            const target = list[0];
            if (target) {
              setActiveConversationId(target.id);
            }
          }
        } else {
          setActiveConversationId(null);
          setMessages([]);
        }
      } catch (err) {
        console.error("Failed to load conversations:", err);
      } finally {
        setLoadingConversations(false);
      }
    },
    [activeProject?.id, activeConversationId]
  );

  useEffect(() => {
    loadConversations(true);
  }, [activeProject?.id]);

  // Load messages when active conversation changes
  const loadMessages = useCallback(
    async (convId: string) => {
      if (!activeProject?.id || !convId) return;
      setLoadingMessages(true);
      try {
        const detail = await api.assistant.getConversation(activeProject.id, convId);
        const filtered = (detail?.messages || []).filter(
          (m) => m.sender_type !== "system" && !m.content?.startsWith("Investigation Checkpoint:")
        );
        setMessages(filtered);
      } catch (err) {
        console.error("Failed to load conversation detail:", err);
        setMessages([]);
      } finally {
        setLoadingMessages(false);
      }
    },
    [activeProject?.id]
  );

  useEffect(() => {
    if (activeConversationId) {
      loadMessages(activeConversationId);
    }
  }, [activeConversationId, loadMessages]);

  // Create new conversation thread
  const handleCreateNewThread = async (title?: string) => {
    if (!activeProject?.id) return;
    try {
      const threadTitle = title || `Investigation #${conversations.length + 1}`;
      const newConv = await api.assistant.createConversation(activeProject.id, threadTitle);
      addToast({
        type: "success",
        title: "Thread Created",
        message: `New conversation "${threadTitle}" opened.`,
      });
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
      setMessages([]);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to create conversation";
      addToast({
        type: "error",
        title: "Creation Error",
        message: errorMsg,
      });
    }
  };

  // Delete conversation thread
  const handleDeleteThread = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeProject?.id) return;
    try {
      await api.assistant.deleteConversation(activeProject.id, convId);
      addToast({
        type: "info",
        title: "Thread Removed",
        message: "Assistant conversation deleted.",
      });
      const updated = conversations.filter((c) => c.id !== convId);
      setConversations(updated);
      if (activeConversationId === convId) {
        if (updated.length > 0 && updated[0]) {
          setActiveConversationId(updated[0].id);
        } else {
          setActiveConversationId(null);
          setMessages([]);
        }
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to delete conversation";
      addToast({
        type: "error",
        title: "Deletion Failed",
        message: errorMsg,
      });
    }
  };

  // Submit question turn
  const handleAsk = async (questionText?: string) => {
    const q = (questionText || inputValue).trim();
    if (!q || !activeProject?.id) return;

    if (!questionText) {
      setInputValue("");
    }

    let targetConvId = activeConversationId;

    // Auto-create thread if none exists
    if (!targetConvId) {
      try {
        const threadTitle = q.length > 40 ? q.slice(0, 37) + "..." : q;
        const newConv = await api.assistant.createConversation(activeProject.id, threadTitle);
        targetConvId = newConv.id;
        setActiveConversationId(newConv.id);
        setConversations((prev) => [newConv, ...prev]);
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "Failed to start thread";
        addToast({
          type: "error",
          title: "Session Error",
          message: errorMsg,
        });
        return;
      }
    }

    // Optimistic user message
    const tempUserMsg: AssistantMessage = {
      id: `temp-user-${Date.now()}`,
      conversation_id: targetConvId,
      sender_type: "user",
      content: q,
      citations: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setAsking(true);
    setLiveInvestigationStage("initiating");
    setLiveInvestigationEvents(["Understanding your question..."]);
    setLiveStreamingAnswer("");

    try {
      const domainsFilter = selectedDomain === "all" ? undefined : [selectedDomain];

      // 1. Start live investigation session
      let invId: string | null = null;
      try {
        const invStart = await api.assistant.startInvestigation(activeProject.id, targetConvId, {
          question: q,
          mode: retrievalMode,
          response_mode: responseMode,
          include_domains: domainsFilter,
        });
        invId = invStart.investigation_id;
      } catch (startErr) {
        console.warn("Live investigation start failed, falling back to sync askQuestion:", startErr);
      }

      // 2. If investigation ID returned, listen to live SSE event stream
      if (invId) {
        const token =
          (typeof window !== "undefined" && localStorage.getItem("handover_access_token")) ||
          (typeof window !== "undefined" && localStorage.getItem("access_token"));
        const sseUrl = `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/v1/projects/${activeProject.id}/assistant/investigations/${invId}/events`;

        let lastEventId = 0;
        let eventStreamClosed = false;

        const processSseLine = (line: string) => {
          if (line.startsWith("event: ")) {
            const ev = line.slice(7).trim();
            if (ev === "node_started" || ev === "plan_created") {
              setLiveInvestigationStage("planning");
              setLiveInvestigationEvents((p) => [...p, "Searching project knowledge..."]);
            } else if (ev === "retrieval_started" || ev === "retrieval_progress") {
              setLiveInvestigationStage("retrieving");
              setLiveInvestigationEvents((p) => [...p, "Reviewing relevant evidence..."]);
            } else if (ev === "agent_selected" || ev === "agent_started") {
              setLiveInvestigationStage("delegating");
              setLiveInvestigationEvents((p) => [...p, "Consulting specialized project intelligence..."]);
            } else if (ev === "synthesis_started") {
              setLiveInvestigationStage("synthesizing");
              setLiveInvestigationEvents((p) => [...p, "Preparing your answer..."]);
            } else if (ev === "token_delta") {
              setLiveInvestigationStage("streaming");
            } else if (ev === "investigation_completed") {
              eventStreamClosed = true;
            }
          } else if (line.startsWith("id: ")) {
            const parsedId = parseInt(line.slice(4).trim(), 10);
            if (!isNaN(parsedId)) lastEventId = parsedId;
          } else if (line.startsWith("data: ")) {
            try {
              const dataObj = JSON.parse(line.slice(6).trim());
              const delta = dataObj.payload?.delta || dataObj.payload?.chunk;
              if (delta) {
                setLiveStreamingAnswer((prev) => prev + delta);
              }
            } catch {
              // Non-JSON SSE payload
            }
          }
        };

        try {
          const sseResp = await fetch(sseUrl, {
            headers: {
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
              "Last-Event-ID": String(lastEventId),
            },
          });

          if (sseResp.ok && sseResp.body) {
            const reader = sseResp.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";

            while (!eventStreamClosed) {
              const { value, done } = await reader.read();
              if (done) break;
              buf += decoder.decode(value, { stream: true });
              const lines = buf.split("\n");
              buf = lines.pop() || "";
              for (const l of lines) {
                processSseLine(l);
              }
            }
          }
        } catch (sseErr) {
          console.warn("SSE stream interrupted, fetching finalized state:", sseErr);
        }

        // Fetch finalized investigation state
        try {
          const finalState = await api.assistant.getInvestigation(activeProject.id, invId);
          if (
            finalState &&
            finalState.raw_answer &&
            !finalState.raw_answer.startsWith("Investigation Checkpoint:")
          ) {
            const mappedClaims = (finalState.claims || []).map((c) => ({
              claim_text: c.claim_text,
              citation_labels: c.citation_labels,
              confidence: 0.95,
            }));

            const mappedCitations = (finalState.validated_citations || []).map((vc, idx) => ({
              id: `cit-${idx}`,
              message_id: `inv-msg-${invId}`,
              citation_label: vc.citation_label,
              citation_order: idx + 1,
              evidence_id: `ev-${idx}`,
              source_title: vc.source_title,
              source_provider: vc.source_provider,
              excerpt: vc.excerpt || "",
              is_verified: true,
            }));

            const assistantMsg: AssistantMessage = {
              id: `inv-msg-${invId}`,
              conversation_id: targetConvId,
              sender_type: "assistant",
              content: finalState.raw_answer,
              answer_status: (finalState.answer_status as AssistantAnswerStatus) || "answered",
              response_mode: finalState.response_mode || responseMode,
              structured_payload_json: {
                claims: mappedClaims,
                conflicts: finalState.conflicts || [],
                uncertainty: finalState.uncertainty || "",
                missing_information: finalState.missing_information || [],
                suggested_followup_questions: finalState.suggested_followups || [],
                response_mode: finalState.response_mode || responseMode,
              },
              citations: mappedCitations,
              model_name: "qwen3:8b",
              created_at: new Date().toISOString(),
            };

            setMessages((prev) => [...prev, assistantMsg]);
            if (mappedCitations.length > 0 && mappedCitations[0]) {
              setActiveCitationLabel(mappedCitations[0].citation_label);
            }
            return;
          }
        } catch (stateErr) {
          console.warn("Failed to retrieve final investigation state directly, falling back to askQuestion:", stateErr);
        }
      }

      // Synchronous fallback
      const maxCits = responseMode === "deep_research" ? 14 : responseMode === "deep_think" ? 12 : 8;
      const answerRes = await api.assistant.askQuestion(activeProject.id, targetConvId, {
        question: q,
        mode: retrievalMode,
        response_mode: responseMode,
        include_domains: domainsFilter,
        max_citations: maxCits,
      });

      const assistantMsg: AssistantMessage = {
        id: answerRes.message_id,
        conversation_id: answerRes.conversation_id,
        sender_type: "assistant",
        content: answerRes.answer,
        answer_status: answerRes.answer_status,
        response_mode: answerRes.response_mode || responseMode,
        structured_payload_json: {
          claims: answerRes.claims,
          conflicts: answerRes.conflicts,
          uncertainty: answerRes.uncertainty,
          missing_information: answerRes.missing_information,
          suggested_followup_questions: answerRes.suggested_followup_questions,
          query_type: answerRes.query_type,
          response_mode: answerRes.response_mode || responseMode,
          research_report: answerRes.research_report,
          deep_think: answerRes.deep_think,
          deep_extract: answerRes.deep_extract,
        },
        citations: answerRes.citations || [],
        model_name: answerRes.model_name,
        duration_ms: answerRes.duration_ms,
        retrieval_run_id: answerRes.retrieval_run_id,
        created_at: answerRes.created_at,
      };

      setMessages((prev) => [...prev, assistantMsg]);

      if (answerRes.citations && answerRes.citations.length > 0 && answerRes.citations[0]) {
        setActiveCitationLabel(answerRes.citations[0].citation_label);
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to retrieve evidence-grounded answer";
      addToast({
        type: "error",
        title: "Assistant Error",
        message: errorMsg,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `temp-err-${Date.now()}`,
          conversation_id: targetConvId!,
          sender_type: "assistant",
          content: `⚠️ Unable to retrieve project information: ${errorMsg}. Please ensure the AI service is reachable.`,
          answer_status: "declined",
          citations: [],
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setAsking(false);
    }
  };

  // Submit feedback
  const handleFeedback = async (messageId: string, type: "helpful" | "unhelpful") => {
    if (!activeProject?.id) return;
    try {
      await api.assistant.submitFeedback(activeProject.id, messageId, {
        feedback_type: type,
      });
      setFeedbackGiven((prev) => ({ ...prev, [messageId]: type }));
      addToast({
        type: "success",
        title: "Feedback Recorded",
        message: type === "helpful" ? "Marked as helpful." : "Marked as needing improvement.",
      });
    } catch {
      // Fallback
    }
  };

  // Handle citation click
  const handleCitationClick = (citationLabel: string) => {
    setActiveCitationLabel(citationLabel);
    if (!rightPanelOpen) {
      setRightPanelOpen(true);
    }
    const element = citationRefs.current[citationLabel];
    if (element && typeof element.scrollIntoView === "function") {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  // Latest assistant message and citations
  const latestAssistantMessage = useMemo(() => {
    return [...messages].reverse().find((m) => m.sender_type === "assistant");
  }, [messages]);

  const activeCitations = useMemo(() => {
    return latestAssistantMessage?.citations || [];
  }, [latestAssistantMessage]);

  // Group citations for Right Panel breakdown
  const filteredCitations = useMemo(() => {
    if (evidenceFilterTab === "all") return activeCitations;
    if (evidenceFilterTab === "jira") {
      return activeCitations.filter((c) => c.source_provider?.toLowerCase().includes("jira"));
    }
    if (evidenceFilterTab === "github") {
      return activeCitations.filter(
        (c) =>
          c.source_provider?.toLowerCase().includes("github") ||
          c.source_provider?.toLowerCase().includes("commit")
      );
    }
    if (evidenceFilterTab === "documents") {
      return activeCitations.filter(
        (c) =>
          c.source_provider?.toLowerCase().includes("document") ||
          c.source_provider?.toLowerCase().includes("upload") ||
          c.source_provider?.toLowerCase().includes("pdf")
      );
    }
    if (evidenceFilterTab === "findings") {
      return activeCitations.filter((c) => c.knowledge_item_id != null || c.is_verified);
    }
    return activeCitations;
  }, [activeCitations, evidenceFilterTab]);

  // Counts by provider
  const countsByProvider = useMemo(() => {
    return {
      all: activeCitations.length,
      jira: activeCitations.filter((c) => c.source_provider?.toLowerCase().includes("jira")).length,
      github: activeCitations.filter(
        (c) =>
          c.source_provider?.toLowerCase().includes("github") ||
          c.source_provider?.toLowerCase().includes("commit")
      ).length,
      documents: activeCitations.filter(
        (c) =>
          c.source_provider?.toLowerCase().includes("document") ||
          c.source_provider?.toLowerCase().includes("upload") ||
          c.source_provider?.toLowerCase().includes("pdf")
      ).length,
      findings: activeCitations.filter((c) => c.knowledge_item_id != null || c.is_verified).length,
    };
  }, [activeCitations]);

  // Render formatted answer with interactive [S1] chips
  const renderFormattedAnswer = (text: string) => {
    const parts = text.split(/(\[S?\d+\])/g);
    return parts.map((part, idx) => {
      const match = part.match(/^\[(S?\d+)\]$/);
      if (match && match[1]) {
        const label = match[1];
        const isActive = activeCitationLabel === label;
        return (
          <button
            key={idx}
            type="button"
            onClick={() => handleCitationClick(label)}
            className={`inline-flex items-center mx-0.5 px-1.5 py-0.2 rounded text-[11px] font-mono font-bold transition-all shadow-2xs ${
              isActive
                ? "bg-blue-600 text-white ring-2 ring-blue-400 scale-105"
                : "bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
            }`}
            title={`View evidence record [${label}]`}
          >
            {part}
          </button>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  const handleCopyJson = (data: unknown, id: string) => {
    try {
      navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopiedExtractId(id);
      setTimeout(() => setCopiedExtractId(null), 2000);
      addToast({
        type: "success",
        title: "Copied",
        message: "Data copied to clipboard.",
      });
    } catch {
      addToast({
        type: "error",
        title: "Copy Failed",
        message: "Failed to copy to clipboard.",
      });
    }
  };

  // Filtered threads list
  const filteredThreads = useMemo(() => {
    if (!searchThreadQuery.trim()) return conversations;
    const q = searchThreadQuery.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, searchThreadQuery]);

  // Mode descriptions for the clean popover
  const modeConfigs = [
    {
      id: "standard",
      label: "Standard",
      description: "Direct answers grounded in verified project sources",
      icon: Sparkles,
      color: "text-blue-600",
    },
    {
      id: "deep_research",
      label: "Deep Research",
      description: "Comprehensive multi-source report with recommendations",
      icon: BookOpen,
      color: "text-indigo-600",
    },
    {
      id: "deep_think",
      label: "Deep Think",
      description: "Causal analysis and architecture trade-offs",
      icon: Brain,
      color: "text-purple-600",
    },
    {
      id: "deep_extract",
      label: "Deep Extract",
      description: "Structured table extraction with JSON export",
      icon: Table,
      color: "text-sky-600",
    },
  ];

  // Minimal Composer Component used both in Welcome Flow and Active Chat
  const renderComposer = () => (
    <div className="relative w-full">
      {/* Settings Popover opened via '+' */}
      {showSettingsPopover && (
        <div
          ref={popoverRef}
          className="absolute bottom-14 left-0 w-76 sm:w-80 bg-white/95 backdrop-blur-xl border border-slate-200/90 shadow-[0_16px_50px_rgba(0,35,90,0.14)] rounded-2xl p-3.5 space-y-3 z-50 animate-fade-in text-xs"
        >
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="font-bold text-slate-900 text-xs">Assistant Settings</span>
            <button
              type="button"
              onClick={() => setShowSettingsPopover(false)}
              className="text-slate-400 hover:text-slate-600 p-0.5"
            >
              <X className="size-3.5" />
            </button>
          </div>

          {/* Assistant Mode */}
          <div className="space-y-1.5">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              Mode
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {modeConfigs.map((mode) => {
                const Icon = mode.icon;
                const isSelected = responseMode === mode.id;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => setResponseMode(mode.id as AssistantResponseMode)}
                    className={`p-2 rounded-xl border text-left transition flex flex-col gap-0.5 ${
                      isSelected
                        ? "bg-blue-50 border-blue-400 ring-1 ring-blue-400 text-blue-950 font-semibold"
                        : "bg-white border-slate-200 hover:bg-slate-50 text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <Icon className={`size-3.5 ${mode.color}`} />
                      <span className="text-[11px]">{mode.label}</span>
                    </div>
                    <span className="text-[9px] text-slate-400 line-clamp-1">
                      {mode.description}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Domain Selector */}
          <div className="space-y-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              Knowledge Domain
            </span>
            <select
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value)}
              className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-slate-700 focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            >
              {DOMAINS_LIST.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          {/* Retrieval Strategy */}
          <div className="space-y-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              Search Method
            </span>
            <select
              value={retrievalMode}
              onChange={(e) => setRetrievalMode(e.target.value as "hybrid" | "keyword" | "semantic")}
              className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-slate-700 focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            >
              <option value="hybrid">Smart Search (Vector + Keyword)</option>
              <option value="keyword">Keyword Search</option>
              <option value="semantic">Semantic Search</option>
            </select>
          </div>
        </div>
      )}

      {/* Minimal Composer Pill */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleAsk();
        }}
        className="w-full bg-white/95 backdrop-blur-xl border border-blue-200/90 shadow-[0_8px_30px_rgba(37,99,235,0.12)] rounded-full px-2 py-1.5 flex items-center gap-2 transition focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-400/20"
      >
        {/* '+' Button to toggle Settings Popover */}
        <button
          type="button"
          onClick={() => setShowSettingsPopover((prev) => !prev)}
          className={`size-9 rounded-full flex items-center justify-center transition shrink-0 ${
            showSettingsPopover
              ? "bg-blue-600 text-white shadow-sm"
              : "bg-slate-100 hover:bg-slate-200 text-slate-700"
          }`}
          title="Assistant Modes &amp; Search Settings"
        >
          <Plus className="size-4" />
        </button>

        {/* Active non-standard indicators (compact tags) */}
        {responseMode !== "standard" && (
          <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-800 shrink-0">
            {responseMode === "deep_research"
              ? "Research"
              : responseMode === "deep_think"
              ? "Think"
              : "Extract"}
          </span>
        )}

        {selectedDomain !== "all" && (
          <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700 truncate max-w-[100px] shrink-0">
            {DOMAINS_LIST.find((d) => d.id === selectedDomain)?.label}
          </span>
        )}

        {/* Main Question Input Field */}
        <input
          type="text"
          placeholder="Ask a question about the project (e.g. architecture, ownership, decisions)..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={asking}
          className="flex-1 bg-transparent px-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-hidden"
        />

        {/* Blue Circular Send Button */}
        <button
          type="submit"
          disabled={!inputValue.trim() || asking}
          className="size-9 rounded-full bg-blue-600 hover:bg-blue-700 active:scale-95 text-white flex items-center justify-center shadow-md transition disabled:opacity-40 disabled:hover:bg-blue-600 disabled:active:scale-100 shrink-0"
          title="Ask Question"
        >
          <Send className="size-4" />
        </button>
      </form>
    </div>
  );

  return (
    <div className="relative h-[calc(100vh-64px)] w-full flex flex-col bg-gradient-to-b from-[#f0f6ff]/40 via-[#f8fbff]/70 to-[#f0f6ff]/40 text-slate-800 overflow-hidden">
      {/* ------------------------------------------------------------- */}
      {/* Top Bar Header & Breadcrumbs                                  */}
      {/* ------------------------------------------------------------- */}
      <header className="w-full border-b border-blue-100/70 bg-white/70 backdrop-blur-md px-4 sm:px-6 py-2.5 flex items-center justify-between gap-4 z-20 shrink-0">
        {/* Left: Breadcrumbs & Page Identity */}
        <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
          <Bot className="size-4 text-blue-600" />
          <span className="text-slate-400">AI Assistant</span>
          <ChevronRight className="size-3 text-slate-300" />
          <span className="font-semibold text-slate-900">Project Knowledge Assistant</span>
        </div>

        {/* Right: Actions Lockup */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleCreateNewThread()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition"
          >
            <Plus className="size-3.5" />
            <span>New Thread</span>
          </button>

          <Link
            href="/evidence"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs transition"
          >
            <Database className="size-3.5 text-slate-500" />
            <span>Evidence Center</span>
          </Link>

          <button
            onClick={() => {
              if (activeConversationId) loadMessages(activeConversationId);
              loadConversations();
            }}
            disabled={loadingConversations || loadingMessages}
            className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 shadow-2xs transition disabled:opacity-50"
            title="Refresh active thread"
          >
            <RefreshCw className={`size-3.5 ${loadingConversations || loadingMessages ? "animate-spin" : ""}`} />
          </button>

          <button
            type="button"
            className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 shadow-2xs transition relative"
            title="Notifications"
          >
            <Bell className="size-3.5" />
            <span className="absolute top-1 right-1 size-1.5 rounded-full bg-blue-600" />
          </button>

          {/* User Initials Avatar */}
          <div className="size-7 rounded-full bg-blue-100 border border-blue-200 text-blue-800 text-xs font-bold flex items-center justify-center shrink-0">
            {user?.full_name
              ? user.full_name
                  .split(" ")
                  .map((n: string) => n[0])
                  .join("")
                  .toUpperCase()
                  .slice(0, 2)
              : user?.email
              ? user.email.slice(0, 2).toUpperCase()
              : "SU"}
          </div>
        </div>
      </header>

      {/* ------------------------------------------------------------- */}
      {/* Floating Edge Reopen Controls (When panels are collapsed)     */}
      {/* ------------------------------------------------------------- */}
      {!leftPanelOpen && (
        <button
          onClick={() => setLeftPanelOpen(true)}
          className="fixed top-20 left-4 z-40 size-8 rounded-full bg-white/90 backdrop-blur-md border border-slate-200/90 shadow-md flex items-center justify-center text-slate-600 hover:text-blue-600 hover:border-blue-300 transition"
          title="Open Context & History"
        >
          <ChevronRight className="size-4" />
        </button>
      )}

      {!rightPanelOpen && (
        <button
          onClick={() => setRightPanelOpen(true)}
          className="fixed top-20 right-4 z-40 size-8 rounded-full bg-white/90 backdrop-blur-md border border-slate-200/90 shadow-md flex items-center justify-center text-slate-600 hover:text-blue-600 hover:border-blue-300 transition"
          title="Open Retrieved Evidence"
        >
          <ChevronLeft className="size-4" />
        </button>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Main Workspace Canvas with Docked Animated Sidebars           */}
      {/* ------------------------------------------------------------- */}
      <div className="relative flex-1 w-full h-[calc(100vh-64px)] flex flex-row p-2 sm:p-3 gap-2 sm:gap-3 overflow-hidden">
        {/* ============================================================ */}
        {/* DOCKED LEFT PANEL: Context & History                         */}
        {/* ============================================================ */}
        <aside
          className={`relative z-20 h-full flex flex-col bg-white/85 backdrop-blur-xl border border-white/90 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl transition-all duration-300 ease-in-out shrink-0 overflow-hidden ${
            leftPanelOpen
              ? "w-72 xl:w-80 opacity-100"
              : "w-0 p-0 m-0 border-0 opacity-0 pointer-events-none"
          }`}
          aria-hidden={!leftPanelOpen}
        >
          {leftPanelOpen && (
            <>
              {/* Panel Header */}
              <div className="p-3 border-b border-blue-50 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <Layers className="size-3.5 text-blue-600" />
                <span className="text-xs font-bold text-slate-900">Context &amp; History</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-400 font-medium">
                  {conversations.length} threads
                </span>
                <button
                  onClick={() => setLeftPanelOpen(false)}
                  className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
                  title="Close panel"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </div>

            {/* Scrollable Content */}
            <div className="p-3 space-y-3.5 overflow-y-auto flex-1 text-xs">
              {/* Project Context */}
              <div className="space-y-1">
                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Project Context
                </div>
                <div className="p-2.5 rounded-xl bg-white/70 border border-blue-100/70 shadow-2xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 truncate">
                      <Folder className="size-3.5 text-blue-600 shrink-0" />
                      <span className="font-bold text-slate-900 truncate">
                        {activeProject?.name || "Project Workspace"}
                      </span>
                    </div>
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/60">
                      Active
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    <User className="size-3 text-slate-400" />
                    <span>{user?.full_name || user?.email || "standard_user"}</span>
                    <span>·</span>
                    <span>Project Member</span>
                  </div>
                  <div className="pt-1.5 border-t border-slate-100 flex items-center gap-1.5 text-[10px] text-slate-500">
                    <ShieldCheck className="size-3 text-blue-600 shrink-0" />
                    <span>Only information you are allowed to access is used. Citations fail-closed.</span>
                  </div>
                </div>
              </div>

              {/* Conversation History */}
              <div className="space-y-1.5 flex flex-col">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                    Conversation History
                  </span>
                  <button
                    onClick={() => handleCreateNewThread()}
                    className="text-[10px] font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    <Plus className="size-3" />
                    <span>New</span>
                  </button>
                </div>

                {/* Thread search */}
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 size-3 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search threads..."
                    value={searchThreadQuery}
                    onChange={(e) => setSearchThreadQuery(e.target.value)}
                    className="w-full pl-7 pr-2 py-1 text-xs bg-white/70 border border-slate-200/80 rounded-lg focus:bg-white focus:outline-hidden focus:ring-1 focus:ring-blue-500 text-slate-800 placeholder-slate-400 transition"
                  />
                </div>

                {/* Thread list */}
                <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
                  {loadingConversations ? (
                    <ListSkeleton variant="thread" count={2} />
                  ) : filteredThreads.length === 0 ? (
                    <div className="p-3 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl space-y-0.5 bg-white/40">
                      <div className="font-semibold text-slate-600 text-[11px]">No conversations yet</div>
                      <div className="text-[10px] text-slate-400">
                        Start a new thread to begin an investigation.
                      </div>
                    </div>
                  ) : (
                    filteredThreads.map((conv) => {
                      const isActive = conv.id === activeConversationId;
                      return (
                        <div
                          key={conv.id}
                          onClick={() => setActiveConversationId(conv.id)}
                          className={`group p-2 rounded-lg border text-xs cursor-pointer transition-all flex items-center justify-between gap-2 ${
                            isActive
                              ? "bg-blue-50/90 border-blue-200 font-semibold text-blue-950 shadow-2xs"
                              : "bg-white/60 border-slate-200/70 hover:bg-white text-slate-700"
                          }`}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="truncate">{conv.title}</div>
                            <div className="flex items-center gap-1 text-[9px] text-slate-400 mt-0.5">
                              <Clock className="size-2.5" />
                              <span>
                                {conv.last_message_at
                                  ? new Date(conv.last_message_at).toLocaleTimeString([], {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })
                                  : new Date(conv.created_at).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => handleDeleteThread(conv.id, e)}
                            className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 p-1 rounded transition-opacity"
                            title="Delete thread"
                          >
                            <Trash2 className="size-3" />
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Quick Questions List */}
              <div className="space-y-1 pt-1">
                <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  <Sparkles className="size-3 text-blue-600" />
                  <span>Quick Questions</span>
                </div>
                <div className="space-y-1">
                  {QUICK_QUESTIONS.map((item, idx) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handleAsk(item.question)}
                        disabled={asking}
                        className="w-full text-left p-1.5 rounded-lg border border-slate-200/80 bg-white/70 hover:bg-white hover:border-blue-300 transition text-[11px] text-slate-700 flex items-center justify-between gap-1.5 group disabled:opacity-50 shadow-2xs"
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Icon className="size-3 text-blue-600 shrink-0" />
                          <span className="font-medium text-slate-800 truncate group-hover:text-blue-900">
                            {item.title}
                          </span>
                        </div>
                        <ChevronRight className="size-3 text-slate-400 group-hover:text-blue-600 shrink-0" />
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Edge Collapse Button */}
            <button
              onClick={() => setLeftPanelOpen(false)}
              className="absolute -right-3 top-1/2 -translate-y-1/2 size-6 rounded-full bg-white border border-slate-200 shadow-md flex items-center justify-center text-slate-400 hover:text-blue-600 transition z-40 hidden lg:flex"
              title="Collapse Context panel"
            >
              <ChevronLeft className="size-3.5" />
            </button>
          </>
        )}
      </aside>

        {/* ============================================================ */}
        {/* MAIN CHAT CANVAS (Expands smoothly when sidebars close)      */}
        {/* ============================================================ */}
        <main
          className={`flex-1 min-w-0 flex flex-col h-full overflow-hidden transition-all duration-300 ease-in-out mx-auto ${
            !leftPanelOpen && !rightPanelOpen
              ? "max-w-4xl xl:max-w-5xl"
              : !leftPanelOpen || !rightPanelOpen
              ? "max-w-3xl xl:max-w-4xl"
              : "max-w-2xl xl:max-w-3xl"
          }`}
        >
          {loadingMessages ? (
            <div className="space-y-4 py-8 max-w-xl mx-auto w-full animate-pulse my-auto">
              <div className="flex justify-end">
                <div className="w-2/3 h-12 bg-blue-100/70 rounded-2xl rounded-tr-xs" />
              </div>
              <div className="flex justify-start">
                <div className="w-4/5 h-28 bg-white rounded-2xl rounded-tl-xs border border-slate-200 p-4 space-y-2">
                  <div className="h-3.5 bg-slate-200 rounded-sm w-3/4" />
                  <div className="h-3 bg-slate-100 rounded-sm w-full" />
                </div>
              </div>
            </div>
          ) : messages.length === 0 ? (
            /* WELCOME STATE: ELEVATED CHAT CANVAS & PROMINENT COMPOSER */
            <div className="h-full flex flex-col items-center justify-start text-center pt-2 sm:pt-4 lg:pt-6 animate-fade-in overflow-y-auto">
              {/* 3D Stacked Glass Thinking Animation */}
              <AssistantThinking3D size="lg" className="mb-0.5 shrink-0" />

              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-0.5">
                Project Knowledge Assistant
              </h2>

              <p className="text-xs text-slate-500 max-w-md mt-0.5 leading-relaxed">
                Ask any question regarding architecture, technical decisions, unfinished work, responsibilities, or risks. Every statement is grounded in authorized project sources with zero fabrication.
              </p>

              {/* Grid of Quick Action Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2.5 w-full max-w-xl shrink-0">
                {QUICK_QUESTIONS.map((p, i) => {
                  const Icon = p.icon;
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={() => handleAsk(p.question)}
                      className="p-2.5 text-left bg-white/80 hover:bg-white border border-slate-200/90 hover:border-blue-300 rounded-xl shadow-2xs hover:shadow-xs transition flex items-center justify-between gap-2.5 group"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <Icon className="size-3.5 text-blue-600 shrink-0" />
                        <span className="font-semibold text-slate-800 text-[11px] truncate group-hover:text-blue-900">
                          {p.title}
                        </span>
                      </div>
                      <ChevronRight className="size-3 text-slate-400 group-hover:text-blue-600 shrink-0" />
                    </button>
                  );
                })}
              </div>

              {/* CHAT BOX (ELEVATED DIRECTLY BENEATH CARDS) */}
              <div className="w-full max-w-xl mt-3 shrink-0">
                {renderComposer()}
              </div>
            </div>
          ) : (
            /* ACTIVE CONVERSATION STATE */
            <div className="flex flex-col h-full overflow-hidden">
              {/* Scrollable Turn History */}
              <div className="flex-1 overflow-y-auto space-y-3 p-2 sm:p-3">
                {messages
                  .filter((m) => m.sender_type !== "system" && !m.content?.startsWith("Investigation Checkpoint:"))
                  .map((msg, index) => {
                  if (msg.sender_type === "user") {
                    return (
                      <div key={msg.id || index} className="flex flex-col items-end">
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-400 uppercase font-semibold mb-1 mr-1">
                          <User className="size-3" />
                          <span>Question</span>
                        </div>
                        <div className="max-w-[85%] bg-blue-50/90 border border-blue-200 text-slate-900 rounded-2xl rounded-tr-xs px-3.5 py-2.5 text-xs leading-relaxed shadow-2xs">
                          {msg.content}
                        </div>
                      </div>
                    );
                  }

                  const isInsufficient = msg.answer_status === "insufficient_evidence";
                  const isPartial =
                    msg.answer_status === "partially_answered" ||
                    Boolean(msg.structured_payload_json?.uncertainty);
                  const hasConflicts =
                    (msg.structured_payload_json?.conflicts &&
                      msg.structured_payload_json.conflicts.length > 0) ||
                    msg.answer_status === "conflicted_evidence";
                  const claims = msg.structured_payload_json?.claims || [];
                  const followups = msg.structured_payload_json?.suggested_followup_questions || [];
                  const isClaimsExpanded = expandedClaims[msg.id];
                  const currentFeedback = feedbackGiven[msg.id];
                  const msgMode =
                    msg.structured_payload_json?.response_mode || msg.response_mode || "standard";

                  const researchReport = msg.structured_payload_json?.research_report;
                  const deepThink = msg.structured_payload_json?.deep_think;
                  const deepExtract = msg.structured_payload_json?.deep_extract;

                  return (
                    <div key={msg.id || index} className="flex items-start gap-3 w-full">
                      {/* Compact 3D Thinking Avatar on the Left */}
                      <div className="shrink-0 pt-0.5" title="Project Knowledge Assistant">
                        <AssistantThinking3D size="xs" isThinking={false} />
                      </div>

                      <div className="flex-1 min-w-0 flex flex-col items-start">
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 uppercase font-semibold mb-1 ml-1">
                          <Bot className="size-3.5 text-blue-600" />
                          <span className="text-slate-900 font-bold">Answer</span>

                        {msgMode === "deep_research" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-100 text-indigo-800 border border-indigo-200 rounded text-[9px] font-bold">
                            <BookOpen className="size-2.5" />
                            Deep Research
                          </span>
                        ) : msgMode === "deep_think" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-100 text-purple-800 border border-purple-200 rounded text-[9px] font-bold">
                            <Brain className="size-2.5" />
                            Deep Think
                          </span>
                        ) : msgMode === "deep_extract" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-sky-100 text-sky-800 border border-sky-200 rounded text-[9px] font-bold">
                            <Table className="size-2.5" />
                            Deep Extract
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200 rounded text-[9px] font-bold">
                            <Sparkles className="size-2.5" />
                            Standard
                          </span>
                        )}
                      </div>

                      <div className="w-full bg-white/95 border border-slate-200/90 rounded-2xl rounded-tl-xs p-3.5 text-xs shadow-xs space-y-3">
                        <div className="text-slate-800 leading-relaxed space-y-2 whitespace-pre-wrap">
                          {renderFormattedAnswer(msg.content)}
                        </div>

                        {/* Structured Reports when present */}
                        {researchReport && (
                          <div className="mt-2.5 p-3 bg-indigo-50/40 border border-indigo-200 rounded-xl space-y-2 text-[11px]">
                            <span className="font-bold text-indigo-900 uppercase tracking-wider block">
                              Multi-Source Research Report
                            </span>
                            <div className="p-2 bg-white rounded border border-indigo-100 text-slate-800">
                              {researchReport.executive_summary}
                            </div>
                          </div>
                        )}

                        {deepThink && (
                          <div className="mt-2.5 p-3 bg-purple-50/40 border border-purple-200 rounded-xl space-y-2 text-[11px]">
                            <span className="font-bold text-purple-900 uppercase tracking-wider block">
                              Reasoning Chain
                            </span>
                            <div className="p-2 bg-white rounded border border-purple-100 text-slate-800">
                              {deepThink.core_hypothesis}
                            </div>
                          </div>
                        )}

                        {deepExtract && deepExtract.records && (
                          <div className="mt-2.5 p-3 bg-sky-50/40 border border-sky-200 rounded-xl space-y-2 text-[11px]">
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-sky-900 uppercase tracking-wider">
                                Entity Extraction: {deepExtract.target_schema}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCopyJson(deepExtract, msg.id)}
                                className="px-2 py-0.5 rounded bg-white hover:bg-sky-100 border border-sky-200 text-sky-800 text-[9px] font-semibold"
                              >
                                {copiedExtractId === msg.id ? "Copied" : "Copy JSON"}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Citation Badges */}
                        {msg.citations && msg.citations.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center gap-1.5">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mr-1">
                              Sources:
                            </span>
                            {msg.citations.map((c, i) => (
                              <button
                                key={i}
                                type="button"
                                onClick={() => handleCitationClick(c.citation_label)}
                                className={`inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-mono font-bold border transition ${
                                  activeCitationLabel === c.citation_label
                                    ? "bg-blue-600 text-white border-blue-700 shadow-xs"
                                    : "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100"
                                }`}
                                title={c.source_title}
                              >
                                <span>[{c.citation_label}]</span>
                                <span className="max-w-[120px] truncate">{c.source_provider}</span>
                              </button>
                            ))}
                          </div>
                        )}

                        {/* States & Warnings */}
                        {isInsufficient && (
                          <div className="p-2.5 bg-amber-50/70 border border-dashed border-amber-300 rounded-lg text-amber-900 text-xs">
                            <div className="font-bold text-[10px] uppercase text-amber-800">
                              Insufficient Evidence
                            </div>
                            <p className="text-[11px] text-amber-800/90 mt-0.5">
                              {msg.structured_payload_json?.uncertainty ||
                                "Available project evidence does not support a fully authoritative answer."}
                            </p>
                          </div>
                        )}

                        {!isInsufficient && isPartial && (
                          <div className="p-2.5 bg-blue-50/50 border border-blue-200 rounded-lg text-blue-950 text-xs">
                            <div className="font-bold text-[10px] uppercase text-blue-800">
                              Partial Evidence
                            </div>
                            <p className="text-[11px] text-blue-900/90 mt-0.5">
                              {msg.structured_payload_json?.uncertainty ||
                                "The answer synthesizes verified records. Some detailed aspects remain unrecorded."}
                            </p>
                          </div>
                        )}

                        {hasConflicts && (
                          <div className="p-2.5 bg-rose-50/70 border border-rose-200 rounded-lg text-rose-900 text-xs">
                            <div className="font-bold text-[10px] uppercase text-rose-800">
                              Conflicting Sources Detected
                            </div>
                            {msg.structured_payload_json?.conflicts?.map((conf, ci) => (
                              <div key={ci} className="text-[11px] text-rose-800/90 mt-0.5">
                                ⚠️ {conf}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Verified Claims Accordion */}
                        {claims.length > 0 && (
                          <div className="pt-1.5 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedClaims((prev) => ({ ...prev, [msg.id]: !prev[msg.id] }))
                              }
                              className="flex items-center justify-between w-full text-left text-[11px] font-semibold text-slate-600 hover:text-slate-900 py-0.5"
                            >
                              <span className="flex items-center gap-1.5">
                                <ShieldCheck className="size-3.5 text-blue-600" />
                                Verified Facts &amp; Sources ({claims.length})
                              </span>
                              {isClaimsExpanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                            </button>

                            {isClaimsExpanded && (
                              <div className="mt-1.5 space-y-1.5 pl-2 border-l-2 border-blue-200">
                                {claims.map((claim, ci) => (
                                  <div key={ci} className="p-1.5 bg-slate-50 rounded border border-slate-200 text-[10px]">
                                    <div className="text-slate-800">{claim.claim_text}</div>
                                    <div className="flex items-center justify-between text-slate-500 mt-1">
                                      <span className="font-semibold text-blue-700">
                                        {Math.round(claim.confidence * 100)}% confidence
                                      </span>
                                      <div className="flex items-center gap-1 font-mono">
                                        {claim.citation_labels.map((cl, cli) => (
                                          <button
                                            key={cli}
                                            type="button"
                                            onClick={() => handleCitationClick(cl)}
                                            className="text-blue-700 hover:underline"
                                          >
                                            [{cl}]
                                          </button>
                                        ))}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Feedback */}
                        <div className="pt-1.5 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
                          <span className="text-[10px] text-slate-400">Grounded in Project Sources</span>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-400">Helpful?</span>
                            <button
                              type="button"
                              onClick={() => handleFeedback(msg.id, "helpful")}
                              disabled={Boolean(currentFeedback)}
                              className={`p-1 rounded hover:bg-slate-100 transition ${
                                currentFeedback === "helpful" ? "text-blue-600 font-bold" : "text-slate-400"
                              }`}
                            >
                              <ThumbsUp className="size-3" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleFeedback(msg.id, "unhelpful")}
                              disabled={Boolean(currentFeedback)}
                              className={`p-1 rounded hover:bg-slate-100 transition ${
                                currentFeedback === "unhelpful" ? "text-rose-600 font-bold" : "text-slate-400"
                              }`}
                            >
                              <ThumbsDown className="size-3" />
                            </button>
                          </div>
                        </div>

                        {/* Follow-ups */}
                        {followups.length > 0 && (
                          <div className="pt-1.5 border-t border-slate-100 flex flex-wrap gap-1">
                            {followups.map((fq, fi) => (
                              <button
                                key={fi}
                                type="button"
                                onClick={() => handleAsk(fq)}
                                disabled={asking}
                                className="px-2 py-0.5 text-[10px] rounded-full bg-slate-100 hover:bg-blue-50 hover:text-blue-900 border border-slate-200 text-slate-700 transition"
                              >
                                {fq}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* In-Flight Responding Turn (Small 3D Thinking Animation on the Left) */}
              {asking && (
                <div className="flex items-start gap-3 w-full animate-fade-in">
                  {/* Small 3D Thinking Animation on the Left */}
                  <div className="shrink-0 pt-0.5" title="Assistant Thinking">
                    <AssistantThinking3D size="sm" isThinking={true} />
                  </div>

                  {/* Responding Assistant Bubble on the Right */}
                  <div className="flex-1 min-w-0 bg-white/95 border border-blue-200/90 rounded-2xl rounded-tl-xs p-3.5 shadow-xs space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900">
                          Project Knowledge Assistant
                        </span>
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200/60 rounded-full">
                          <span className="size-1.5 rounded-full bg-blue-500 animate-ping" />
                          Answering...
                        </span>
                      </div>
                    </div>

                    {/* Contextual progress stage */}
                    <div className="flex items-center gap-2 text-xs text-slate-600 font-medium">
                      <span className="size-1.5 rounded-full bg-blue-600 animate-pulse" />
                      <span>
                        {liveInvestigationStage === "planning"
                          ? "Searching project knowledge..."
                          : liveInvestigationStage === "retrieving"
                          ? "Reviewing relevant evidence..."
                          : liveInvestigationStage === "synthesizing"
                          ? "Preparing your answer..."
                          : "Understanding your question..."}
                      </span>
                    </div>

                    {/* Live Streaming Answer or Shimmer */}
                    {liveStreamingAnswer ? (
                      <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl font-mono text-[11px] leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap text-slate-800">
                        {liveStreamingAnswer}
                      </div>
                    ) : (
                      <div className="space-y-1.5 pt-1 animate-pulse" aria-hidden="true">
                        <div className="h-2.5 bg-blue-100/70 rounded w-5/6" />
                        <div className="h-2.5 bg-slate-100 rounded w-full" />
                        <div className="h-2.5 bg-slate-100 rounded w-3/4" />
                      </div>
                    )}
                  </div>
                </div>
              )}

                <div ref={messagesEndRef} />
              </div>

              {/* DOCKED CHAT BOX FOR ACTIVE CONVERSATION */}
              <div className="p-3 bg-white/70 backdrop-blur-md border-t border-blue-100/60 shrink-0">
                {renderComposer()}
              </div>
            </div>
          )}
        </main>

        {/* ============================================================ */}
        {/* DOCKED RIGHT PANEL: Retrieved Evidence                       */}
        {/* ============================================================ */}
        <aside
          className={`relative z-20 h-full flex flex-col bg-white/85 backdrop-blur-xl border border-white/90 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl transition-all duration-300 ease-in-out shrink-0 overflow-hidden ${
            rightPanelOpen
              ? "w-76 xl:w-88 opacity-100"
              : "w-0 p-0 m-0 border-0 opacity-0 pointer-events-none"
          }`}
          aria-hidden={!rightPanelOpen}
        >
          {rightPanelOpen && (
            <>
              {/* Panel Header */}
              <div className="p-3 border-b border-blue-50 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <FileText className="size-3.5 text-blue-600" />
                  <span className="text-xs font-bold text-slate-900">Retrieved Evidence</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400 font-medium">
                    {activeCitations.length} sources
                  </span>
                  <button
                    onClick={() => setRightPanelOpen(false)}
                    className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
                    title="Close panel"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              </div>

              {/* Category Tabs: Only render when citations exist to prevent empty horizontal scrollbar */}
              {activeCitations.length > 0 && (
                <div className="flex border-b border-slate-100 px-3 pt-1 gap-1 text-[10px] bg-slate-50/50 overflow-x-hidden">
                  <button
                    type="button"
                    onClick={() => setEvidenceFilterTab("all")}
                    className={`pb-1 px-1.5 font-semibold border-b-2 transition ${
                      evidenceFilterTab === "all"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    All ({countsByProvider.all})
                  </button>
                  <button
                    type="button"
                    onClick={() => setEvidenceFilterTab("jira")}
                    className={`pb-1 px-1.5 font-semibold border-b-2 transition ${
                      evidenceFilterTab === "jira"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Jira ({countsByProvider.jira})
                  </button>
                  <button
                    type="button"
                    onClick={() => setEvidenceFilterTab("github")}
                    className={`pb-1 px-1.5 font-semibold border-b-2 transition ${
                      evidenceFilterTab === "github"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    GitHub ({countsByProvider.github})
                  </button>
                  <button
                    type="button"
                    onClick={() => setEvidenceFilterTab("documents")}
                    className={`pb-1 px-1.5 font-semibold border-b-2 transition ${
                      evidenceFilterTab === "documents"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Docs ({countsByProvider.documents})
                  </button>
                </div>
              )}

              {/* Evidence Content */}
              <div className="flex-1 p-3 overflow-y-auto space-y-2">
                {filteredCitations.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center p-6 text-center text-slate-400">
                    <div className="size-14 rounded-2xl bg-blue-50/70 border border-blue-100 flex items-center justify-center text-blue-500 mb-2.5 shadow-2xs">
                      <FileText className="size-7 stroke-[1.5]" />
                    </div>
                    <div className="text-xs font-bold text-slate-800">No Retrieved Evidence</div>
                    <p className="text-[11px] text-slate-400 max-w-xs mt-1 leading-relaxed">
                      Ask a question in the center panel. Authorized supporting records will appear here with full provenance and direct quotations.
                    </p>
                  </div>
                ) : (
                  filteredCitations.map((citation, idx) => {
                    const isSelected = activeCitationLabel === citation.citation_label;
                    const isGitHub = citation.source_provider?.toLowerCase().includes("github");
                    const isJira = citation.source_provider?.toLowerCase().includes("jira");
                    const isDoc = citation.source_provider?.toLowerCase().includes("document");

                    return (
                      <div
                        key={idx}
                        ref={(el) => {
                          citationRefs.current[citation.citation_label] = el;
                        }}
                        onClick={() => setActiveCitationLabel(citation.citation_label)}
                        className={`p-2.5 rounded-xl border text-xs transition-all space-y-1.5 cursor-pointer ${
                          isSelected
                            ? "bg-blue-50/70 border-blue-500 ring-2 ring-blue-500/20 shadow-xs"
                            : "bg-white/80 border-slate-200/80 hover:border-slate-300 shadow-2xs"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex items-center gap-1.5">
                            <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-blue-600 text-white shadow-2xs">
                              [{citation.citation_label}]
                            </span>
                            <span
                              className={`inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[9px] font-semibold border ${
                                isGitHub
                                  ? "bg-purple-50 text-purple-800 border-purple-200"
                                  : isJira
                                  ? "bg-blue-50 text-blue-800 border-blue-200"
                                  : isDoc
                                  ? "bg-teal-50 text-teal-800 border-teal-200"
                                  : "bg-slate-100 text-slate-700 border-slate-200"
                              }`}
                            >
                              {isGitHub ? (
                                <GitCommit className="size-2.5" />
                              ) : isDoc ? (
                                <FileText className="size-2.5" />
                              ) : (
                                <Database className="size-2.5" />
                              )}
                              {citation.source_provider}
                            </span>
                          </div>
                          {citation.is_verified && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[9px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                              <CheckCircle2 className="size-2.5 text-emerald-600" />
                              Verified
                            </span>
                          )}
                        </div>

                        <div className="font-bold text-slate-900 text-xs leading-snug break-words">
                          {citation.source_title}
                        </div>

                        <div className="p-2 bg-slate-50/80 rounded-lg border border-slate-200/80 text-slate-700 text-[10px] italic leading-relaxed whitespace-pre-wrap">
                          &quot;{citation.excerpt}&quot;
                        </div>

                        <div className="flex items-center justify-end pt-0.5">
                          {citation.source_url ? (
                            <a
                              href={citation.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                            >
                              <span>Open Source Record</span>
                              <ExternalLink className="size-2.5" />
                            </a>
                          ) : (
                            <Link
                              href={`/evidence?id=${citation.evidence_id}`}
                              className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                            >
                              <span>View in Evidence Center</span>
                              <ChevronRight className="size-2.5" />
                            </Link>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Edge Collapse Button */}
              <button
                onClick={() => setRightPanelOpen(false)}
                className="absolute -left-3 top-1/2 -translate-y-1/2 size-6 rounded-full bg-white border border-slate-200 shadow-md flex items-center justify-center text-slate-400 hover:text-blue-600 transition z-40 hidden lg:flex"
                title="Collapse Evidence panel"
              >
                <ChevronRight className="size-3.5" />
              </button>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

export default AssistantWorkspaceView;
