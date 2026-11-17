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
  AlertTriangle,
  HelpCircle,
  FileText,
  GitCommit,
  CheckCircle2,
  ThumbsUp,
  ThumbsDown,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Database,
  Layers,
  Search,
  User,
  ArrowRight,
  Hash,
  Clock,
  Check,
  BookOpen,
  Brain,
  Table,
  Copy,
  CheckCheck,
} from "lucide-react";
import Link from "next/link";
import { api } from "../../lib/api";
import { useLiveApp } from "../../context/LiveAppContext";
import type {
  AssistantConversation,
  AssistantMessage,
  AssistantCitation,
  AssistantClaim,
  AssistantAnswerStatus,
  AssistantResponseMode,
} from "../../lib/types";

// Starter prompt recommendations
const STARTER_PROMPTS = [
  {
    title: "Platform Identity & Auth",
    question: "What is the platform identity and authentication architecture?",
    category: "Architecture",
  },
  {
    title: "RTX 4050 VRAM Contention",
    question: "What are the main architecture risks regarding Ollama and RTX 4050 VRAM contention?",
    category: "Risks",
  },
  {
    title: "Storage Provider Decision",
    question: "What are the key architectural decisions regarding dual-provider storage?",
    category: "Decisions",
  },
  {
    title: "Ownership & Responsibilities",
    question: "Who is responsible for platform architecture and cryptographic security?",
    category: "Ownership",
  },
  {
    title: "Unfinished Tasks & Milestones",
    question: "What unfinished tasks and blockers remain for the project transition?",
    category: "Tasks",
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

  // Form input
  const [inputValue, setInputValue] = useState<string>("");
  const [selectedDomain, setSelectedDomain] = useState<string>("all");
  const [retrievalMode, setRetrievalMode] = useState<"hybrid" | "keyword" | "semantic">("hybrid");
  const [responseMode, setResponseMode] = useState<AssistantResponseMode>("standard");

  // Interaction
  const [activeCitationLabel, setActiveCitationLabel] = useState<string | null>(null);
  const [evidenceFilterTab, setEvidenceFilterTab] = useState<string>("all");
  const [expandedClaims, setExpandedClaims] = useState<Record<string, boolean>>({});
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, "helpful" | "unhelpful">>({});
  const [searchThreadQuery, setSearchThreadQuery] = useState<string>("");
  const [copiedExtractId, setCopiedExtractId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const citationRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Auto-scroll messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
        setMessages(detail?.messages || []);
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
        message: `New assistant conversation "${threadTitle}" opened.`,
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
    setLiveInvestigationEvents(["Initializing investigation session..."]);
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
        const token = localStorage.getItem("access_token");
        const sseUrl = `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/v1/projects/${activeProject.id}/assistant/investigations/${invId}/events`;
        
        let lastEventId = 0;
        let eventStreamClosed = false;

        const processSseLine = (line: string) => {
          if (line.startsWith("event: ")) {
            const ev = line.slice(7).trim();
            if (ev === "node_started" || ev === "plan_created") {
              setLiveInvestigationStage("planning");
              setLiveInvestigationEvents((p) => [...p, "Formulating plan & expanding subqueries..."]);
            } else if (ev === "retrieval_started" || ev === "retrieval_progress") {
              setLiveInvestigationStage("retrieving");
              setLiveInvestigationEvents((p) => [...p, "Querying ChromaDB vector index & PostgreSQL full-text search..."]);
            } else if (ev === "agent_selected" || ev === "agent_started") {
              setLiveInvestigationStage("delegating");
              setLiveInvestigationEvents((p) => [...p, "Delegating subtask to specialized dynamic agent worker..."]);
            } else if (ev === "synthesis_started") {
              setLiveInvestigationStage("synthesizing");
              setLiveInvestigationEvents((p) => [...p, "Synthesizing evidence with Ollama Qwen3 8B..."]);
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
              if (dataObj.payload?.chunk) {
                setLiveStreamingAnswer((prev) => prev + dataObj.payload.chunk);
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
          if (finalState && finalState.raw_answer) {
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

      // Synchronous fallback if SSE/Investigation did not yield terminal message
      const maxCits = responseMode === "deep_research" ? 14 : responseMode === "deep_think" ? 12 : 8;
      const answerRes = await api.assistant.askQuestion(activeProject.id, targetConvId, {
        question: q,
        mode: retrievalMode,
        response_mode: responseMode,
        include_domains: domainsFilter,
        max_citations: maxCits,
      });

      // Append assistant message from answer response
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

      // If citations were returned, focus the first one
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
      // Append error message to chat
      setMessages((prev) => [
        ...prev,
        {
          id: `temp-err-${Date.now()}`,
          conversation_id: targetConvId!,
          sender_type: "assistant",
          content: `⚠️ Error during knowledge retrieval: ${errorMsg}. Please verify connection to the Ollama runtime and PostgreSQL full-text search.`,
          answer_status: "declined",
          citations: [],
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setAsking(false);
    }
  };

  // Submit message feedback
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
        message: type === "helpful" ? "Marked response as helpful." : "Marked response as needing improvement.",
      });
    } catch {
      // Fallback
    }
  };

  // Handle citation click: highlight and scroll to Panel 3 card
  const handleCitationClick = (citationLabel: string) => {
    setActiveCitationLabel(citationLabel);
    const element = citationRefs.current[citationLabel];
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  // Extract all citations from the latest assistant message or active thread
  const latestAssistantMessage = useMemo(() => {
    return [...messages].reverse().find((m) => m.sender_type === "assistant");
  }, [messages]);

  const activeCitations = useMemo(() => {
    return latestAssistantMessage?.citations || [];
  }, [latestAssistantMessage]);

  // Group citations for Panel 3 breakdown
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

  // Helper to render answer text with interactive [S1], [S2] chips
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
                ? "bg-emerald-600 text-white ring-2 ring-emerald-400 scale-105"
                : "bg-emerald-100 text-emerald-800 hover:bg-emerald-200 border border-emerald-300"
            }`}
            title={`View evidence record [${label}] in Panel 3`}
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
        message: "Extracted data copied to clipboard as JSON.",
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

  return (
    <div className="flex flex-col min-h-[calc(100vh-64px)] bg-[#f8fafc] text-slate-800 p-6 space-y-6">
      {/* ------------------------------------------------------------- */}
      {/* Top Bar Header & Breadcrumbs                                 */}
      {/* ------------------------------------------------------------- */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-teal-800">
            <span className="inline-block size-2 rounded-full bg-teal-500 animate-pulse" />
            Sidebar: AI ASSISTANT &gt; Project Knowledge Assistant
            <span className="text-slate-400">·</span>
            <span className="text-emerald-700 font-mono lowercase tracking-normal">evidence-grounded answers</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1 flex items-center gap-2">
            Project Knowledge Assistant
          </h1>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            Permission-filtered hybrid RAG assistant with strict source citations, source ACL checks, and uncertainty disclosure.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start md:self-auto">
          <button
            onClick={() => handleCreateNewThread()}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-teal-700 hover:bg-teal-800 text-white shadow-xs transition"
          >
            <Plus className="size-3.5" />
            New Thread
          </button>
          <Link
            href="/evidence"
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-xs transition"
          >
            <Database className="size-3.5 text-slate-500" />
            Go to Evidence Center
          </Link>
          <button
            onClick={() => {
              if (activeConversationId) loadMessages(activeConversationId);
              loadConversations();
            }}
            disabled={loadingConversations || loadingMessages}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-xs transition disabled:opacity-50"
            title="Refresh threads and active turn"
          >
            <RefreshCw className={`size-3.5 ${loadingConversations || loadingMessages ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* 3-Panel Main Workspace Architecture (Matches Wireframe Fig. 8) */}
      {/* ------------------------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 items-start">
        {/* ============================================================ */}
        {/* PANEL 1: CONTEXT (Left Panel)                               */}
        {/* ============================================================ */}
        <div className="lg:col-span-3 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[760px]">
          {/* Header */}
          <div className="bg-[#1e293b] text-white px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <Layers className="size-3.5 text-blue-400" />
              1 CONTEXT
            </span>
            <span className="text-[11px] font-mono text-slate-300 bg-slate-800 px-2 py-0.5 rounded-full">
              {conversations.length} threads
            </span>
          </div>

          <div className="p-3.5 flex flex-col gap-4 overflow-y-auto flex-1">
            {/* Section 1: PROJECT, ROLE */}
            <div>
              <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                PROJECT, ROLE
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-900 truncate">
                    {activeProject?.name || "Skillpassport"}
                  </span>
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                    Active
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-slate-600">
                  <User className="size-3 text-slate-400" />
                  <span className="font-medium text-slate-700">
                    {(user?.roles && user.roles[0]) || "project_manager"}
                  </span>
                  <span className="text-slate-400">·</span>
                  <span className="text-[11px] text-slate-500">Project Member</span>
                </div>
                <div className="pt-2 border-t border-slate-200 flex items-start gap-1.5 text-[11px] text-slate-500 leading-tight">
                  <ShieldCheck className="size-3.5 text-teal-600 shrink-0 mt-0.5" />
                  <span>Strict pre-retrieval source ACL enforcement. Citations fail-closed.</span>
                </div>
              </div>
            </div>

            {/* Section 2: CONVERSATION HISTORY */}
            <div className="flex flex-col flex-1 min-h-[220px]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  CONVERSATION HISTORY
                </span>
                <button
                  onClick={() => handleCreateNewThread()}
                  className="text-[11px] font-semibold text-teal-700 hover:text-teal-900 flex items-center gap-1"
                >
                  <Plus className="size-3" />
                  New
                </button>
              </div>

              {/* Thread search */}
              <div className="relative mb-2">
                <Search className="absolute left-2.5 top-2.5 size-3 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter threads..."
                  value={searchThreadQuery}
                  onChange={(e) => setSearchThreadQuery(e.target.value)}
                  className="w-full pl-7 pr-2 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-md focus:bg-white focus:outline-hidden focus:ring-1 focus:ring-teal-500 text-slate-800 placeholder-slate-400"
                />
              </div>

              {/* Thread list */}
              <div className="space-y-1.5 overflow-y-auto flex-1 pr-1 max-h-[220px]">
                {loadingConversations ? (
                  <div className="p-4 text-center text-xs text-slate-400">Loading threads...</div>
                ) : filteredThreads.length === 0 ? (
                  <div className="p-4 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
                    No conversations found. Click &quot;New&quot; to start.
                  </div>
                ) : (
                  filteredThreads.map((conv) => {
                    const isActive = conv.id === activeConversationId;
                    return (
                      <div
                        key={conv.id}
                        onClick={() => setActiveConversationId(conv.id)}
                        className={`group p-2.5 rounded-lg border text-xs cursor-pointer transition-all flex items-start justify-between gap-2 ${
                          isActive
                            ? "bg-teal-50/80 border-teal-300 shadow-2xs font-medium text-teal-950"
                            : "bg-white border-slate-200 hover:bg-slate-50 text-slate-700"
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="truncate font-semibold">{conv.title}</div>
                          <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mt-1">
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

            {/* Section 3: RECENT QUESTIONS / STARTER PROMPTS */}
            <div>
              <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                RECENT QUESTIONS &amp; PROMPTS
              </div>
              <div className="space-y-1.5">
                {STARTER_PROMPTS.map((prompt, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleAsk(prompt.question)}
                    disabled={asking}
                    className="w-full text-left p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 hover:border-teal-300 transition-colors text-xs text-slate-700 flex items-start justify-between gap-2 group disabled:opacity-50"
                  >
                    <div className="flex-1">
                      <span className="font-medium group-hover:text-teal-900 block">{prompt.title}</span>
                      <span className="text-[10px] text-slate-400 truncate block mt-0.5">{prompt.question}</span>
                    </div>
                    <ArrowRight className="size-3 text-slate-400 group-hover:text-teal-600 shrink-0 mt-1" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* PANEL 2: QUESTION AND ANSWER (Center Panel)                  */}
        {/* ============================================================ */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[760px]">
          {/* Header */}
          <div className="bg-[#0f766e] text-white px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <Bot className="size-3.5 text-emerald-300" />
              2 QUESTION AND ANSWER
            </span>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 text-[10px] font-mono bg-teal-800/80 text-teal-100 px-2 py-0.5 rounded-full border border-teal-600/50">
                <Sparkles className="size-2.5 text-emerald-300" />
                Hybrid RAG: Qwen3 8B
              </span>
            </div>
          </div>

          {/* Conversation Turns Scroll Area */}
          <div className="flex-1 p-4 overflow-y-auto space-y-5 bg-slate-50/50">
            {loadingMessages ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading conversation history...</div>
            ) : messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center p-6 text-center">
                <div className="size-12 rounded-full bg-teal-100 flex items-center justify-center text-teal-700 mb-3">
                  <Bot className="size-6" />
                </div>
                <h3 className="text-sm font-bold text-slate-900">Project Knowledge Assistant</h3>
                <p className="text-xs text-slate-500 max-w-sm mt-1 leading-relaxed">
                  Ask any question regarding architecture, technical decisions, unfinished work, responsibilities, or risks.
                  Every statement is grounded in authorized project sources with zero fabrication.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-5 w-full max-w-md">
                  {STARTER_PROMPTS.slice(0, 4).map((p, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => handleAsk(p.question)}
                      className="p-2 text-left bg-white border border-slate-200 rounded-lg hover:border-teal-400 hover:shadow-2xs transition text-xs"
                    >
                      <div className="font-semibold text-slate-800 text-[11px]">{p.title}</div>
                      <div className="text-[10px] text-slate-400 truncate mt-0.5">{p.question}</div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, index) => {
                if (msg.sender_type === "user") {
                  return (
                    <div key={msg.id || index} className="flex flex-col items-end">
                      <div className="flex items-center gap-1.5 text-[10px] text-slate-400 uppercase font-semibold mb-1 mr-1">
                        <User className="size-3" />
                        <span>QUESTION (user)</span>
                        <span>·</span>
                        <span>
                          {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Now"}
                        </span>
                      </div>
                      <div className="max-w-[85%] bg-blue-50/80 border border-blue-200 text-slate-900 rounded-2xl rounded-tr-xs px-4 py-3 text-xs leading-relaxed shadow-2xs">
                        {msg.content}
                      </div>
                    </div>
                  );
                }

                // Assistant message turn
                const isInsufficient = msg.answer_status === "insufficient_evidence";
                const isPartial = msg.answer_status === "partially_answered" || Boolean(msg.structured_payload_json?.uncertainty);
                const hasConflicts =
                  (msg.structured_payload_json?.conflicts &&
                    msg.structured_payload_json.conflicts.length > 0) ||
                  msg.answer_status === "conflicted_evidence";
                const claims = msg.structured_payload_json?.claims || [];
                const followups = msg.structured_payload_json?.suggested_followup_questions || [];
                const isClaimsExpanded = expandedClaims[msg.id];
                const currentFeedback = feedbackGiven[msg.id];
                const msgMode = msg.structured_payload_json?.response_mode || msg.response_mode || "standard";

                const researchReport = msg.structured_payload_json?.research_report;
                const deepThink = msg.structured_payload_json?.deep_think;
                const deepExtract = msg.structured_payload_json?.deep_extract;

                return (
                  <div key={msg.id || index} className="flex flex-col items-start w-full">
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-500 uppercase font-semibold mb-1 ml-1">
                      <Bot className="size-3 text-teal-600" />
                      <span className="text-teal-900 font-bold">ANSWER</span>

                      {/* Response Mode Badge */}
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
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-teal-100 text-teal-800 border border-teal-200 rounded text-[9px] font-bold">
                          <Sparkles className="size-2.5" />
                          Standard
                        </span>
                      )}

                      {msg.structured_payload_json?.query_type && (
                        <span className="px-1.5 py-0.2 bg-slate-100 text-slate-700 rounded text-[9px] font-mono">
                          {msg.structured_payload_json.query_type}
                        </span>
                      )}
                      {msg.duration_ms && (
                        <span className="text-slate-400 font-mono text-[9px]">
                          {(msg.duration_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                    </div>

                    <div className="w-full bg-white border border-slate-200 rounded-2xl rounded-tl-xs p-4 text-xs shadow-xs space-y-3.5">
                      {/* Main answer text */}
                      <div className="text-slate-800 leading-relaxed space-y-2 whitespace-pre-wrap">
                        {renderFormattedAnswer(msg.content)}
                      </div>

                      {/* ======================================================== */}
                      {/* DEEP RESEARCH STRUCTURED REPORT                          */}
                      {/* ======================================================== */}
                      {researchReport && (
                        <div className="mt-3 p-3.5 bg-indigo-50/40 border border-indigo-200 rounded-xl space-y-3">
                          <div className="flex items-center justify-between border-b border-indigo-100 pb-2">
                            <span className="flex items-center gap-1.5 font-bold text-indigo-900 text-[11px] uppercase tracking-wider">
                              <BookOpen className="size-3.5 text-indigo-600" />
                              Multi-Source Research Report
                            </span>
                            {researchReport.coverage_assessment && (
                              <span className="px-2 py-0.5 text-[10px] font-medium bg-indigo-100 text-indigo-800 rounded-full border border-indigo-200">
                                Coverage: {researchReport.coverage_assessment}
                              </span>
                            )}
                          </div>

                          {/* Executive Summary */}
                          <div className="p-2.5 bg-white rounded-lg border border-indigo-100 text-[11px] text-slate-800 leading-relaxed">
                            <div className="font-bold text-indigo-950 mb-1">Executive Summary:</div>
                            {researchReport.executive_summary}
                          </div>

                          {/* Report Sections */}
                          {researchReport.sections && researchReport.sections.length > 0 && (
                            <div className="space-y-2">
                              {researchReport.sections.map((sec, sIdx) => (
                                <div key={sIdx} className="p-2.5 bg-white rounded-lg border border-slate-200 text-[11px] space-y-1.5">
                                  <div className="flex items-center justify-between">
                                    <span className="font-bold text-slate-900">{sec.section_title}</span>
                                    <div className="flex items-center gap-1 font-mono">
                                      {sec.citation_labels.map((cl, cli) => (
                                        <button
                                          key={cli}
                                          type="button"
                                          onClick={() => handleCitationClick(cl)}
                                          className="text-[10px] text-indigo-700 hover:underline"
                                        >
                                          [{cl}]
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                  <div className="text-slate-700 leading-relaxed">{renderFormattedAnswer(sec.content)}</div>
                                  {sec.key_takeaways && sec.key_takeaways.length > 0 && (
                                    <div className="pt-1 border-t border-slate-100 text-[10px] text-slate-600 space-y-0.5">
                                      <span className="font-semibold text-slate-700">Key Takeaways:</span>
                                      {sec.key_takeaways.map((kt, kti) => (
                                        <div key={kti} className="flex items-center gap-1 text-slate-600 pl-1">
                                          <span>•</span>
                                          <span>{kt}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Cross-Source Corroboration */}
                          {researchReport.cross_source_corroboration && researchReport.cross_source_corroboration.length > 0 && (
                            <div className="p-2.5 bg-white rounded-lg border border-slate-200 text-[11px]">
                              <div className="font-bold text-slate-900 mb-1">Cross-Source Corroboration:</div>
                              <ul className="list-disc pl-4 space-y-0.5 text-slate-700 text-[10px]">
                                {researchReport.cross_source_corroboration.map((c, ci) => (
                                  <li key={ci}>{c}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Actionable Recommendations */}
                          {researchReport.recommendations && researchReport.recommendations.length > 0 && (
                            <div className="p-2.5 bg-indigo-100/50 rounded-lg border border-indigo-200 text-[11px]">
                              <div className="font-bold text-indigo-950 mb-1">Successor Recommendations:</div>
                              <ul className="list-disc pl-4 space-y-0.5 text-indigo-900 text-[10px]">
                                {researchReport.recommendations.map((r, ri) => (
                                  <li key={ri}>{r}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}

                      {/* ======================================================== */}
                      {/* DEEP THINK CAUSAL REASONING                              */}
                      {/* ======================================================== */}
                      {deepThink && (
                        <div className="mt-3 p-3.5 bg-purple-50/40 border border-purple-200 rounded-xl space-y-3">
                          <div className="flex items-center gap-1.5 border-b border-purple-100 pb-2 font-bold text-purple-900 text-[11px] uppercase tracking-wider">
                            <Brain className="size-3.5 text-purple-600" />
                            Causal &amp; Architecture Reasoning Chain
                          </div>

                          {/* Core Hypothesis */}
                          <div className="p-2.5 bg-white rounded-lg border border-purple-100 text-[11px] text-slate-800">
                            <span className="font-bold text-purple-950">Core Hypothesis: </span>
                            {deepThink.core_hypothesis}
                          </div>

                          {/* Causal Chain Steps */}
                          {deepThink.causal_chain && deepThink.causal_chain.length > 0 && (
                            <div className="space-y-2">
                              <div className="text-[10px] font-bold text-purple-950 uppercase tracking-wider">
                                Causal Progression:
                              </div>
                              {deepThink.causal_chain.map((step, stIdx) => (
                                <div key={stIdx} className="p-2.5 bg-white rounded-lg border border-purple-100 text-[11px] space-y-1">
                                  <div className="flex items-center justify-between">
                                    <span className="inline-flex items-center gap-1 font-bold text-purple-900">
                                      <span className="size-4 rounded-full bg-purple-100 text-purple-800 text-[10px] flex items-center justify-center font-bold">
                                        {step.step_number}
                                      </span>
                                      {step.event_or_decision}
                                    </span>
                                    {step.actor_or_source && (
                                      <span className="text-[10px] font-mono text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200">
                                        {step.actor_or_source}
                                      </span>
                                    )}
                                  </div>
                                  {step.consequences && step.consequences.length > 0 && (
                                    <div className="pl-5 text-[10px] text-slate-600 space-y-0.5">
                                      <span className="font-semibold text-slate-700">Consequences:</span>
                                      {step.consequences.map((c, ci) => (
                                        <div key={ci} className="text-slate-600">→ {c}</div>
                                      ))}
                                    </div>
                                  )}
                                  {step.citation_labels && step.citation_labels.length > 0 && (
                                    <div className="pl-5 flex items-center gap-1 font-mono text-[10px]">
                                      <span className="text-slate-400">Supporting:</span>
                                      {step.citation_labels.map((cl, cli) => (
                                        <button
                                          key={cli}
                                          type="button"
                                          onClick={() => handleCitationClick(cl)}
                                          className="text-purple-700 hover:underline"
                                        >
                                          [{cl}]
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Tradeoffs & Risks */}
                          {deepThink.tradeoffs_and_risks && deepThink.tradeoffs_and_risks.length > 0 && (
                            <div className="p-2.5 bg-amber-50/60 rounded-lg border border-amber-200 text-[11px]">
                              <div className="font-bold text-amber-950 mb-1">Architectural Trade-offs &amp; Risks:</div>
                              <ul className="list-disc pl-4 space-y-0.5 text-amber-900 text-[10px]">
                                {deepThink.tradeoffs_and_risks.map((t, ti) => (
                                  <li key={ti}>{t}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}

                      {/* ======================================================== */}
                      {/* DEEP EXTRACT STRUCTURED TABULAR DATA                     */}
                      {/* ======================================================== */}
                      {deepExtract && (
                        <div className="mt-3 p-3.5 bg-sky-50/40 border border-sky-200 rounded-xl space-y-3">
                          <div className="flex items-center justify-between border-b border-sky-100 pb-2">
                            <span className="flex items-center gap-1.5 font-bold text-sky-900 text-[11px] uppercase tracking-wider">
                              <Table className="size-3.5 text-sky-600" />
                              Structured Entity Extraction: {deepExtract.target_schema}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleCopyJson(deepExtract, msg.id)}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-white hover:bg-sky-100 border border-sky-200 text-sky-800 text-[10px] font-semibold transition shadow-2xs"
                              title="Copy structured records as JSON"
                            >
                              {copiedExtractId === msg.id ? (
                                <>
                                  <CheckCheck className="size-3 text-emerald-600" />
                                  <span>Copied JSON</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="size-3" />
                                  <span>Copy JSON</span>
                                </>
                              )}
                            </button>
                          </div>

                          {/* Extracted Table */}
                          {deepExtract.records && deepExtract.records.length > 0 && (
                            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-2xs">
                              <table className="w-full text-left border-collapse text-[11px]">
                                <thead>
                                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-700 font-bold">
                                    <th className="p-2">Entity</th>
                                    <th className="p-2">Category</th>
                                    <th className="p-2">Status</th>
                                    <th className="p-2">Attributes &amp; Provenance</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                  {deepExtract.records.map((rec, rIdx) => (
                                    <tr key={rIdx} className="hover:bg-slate-50/50">
                                      <td className="p-2 font-semibold text-slate-900 whitespace-nowrap">{rec.entity_name}</td>
                                      <td className="p-2 text-slate-600 whitespace-nowrap">
                                        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px]">
                                          {rec.category}
                                        </span>
                                      </td>
                                      <td className="p-2 whitespace-nowrap">
                                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                                          {rec.status_or_state || "Recorded"}
                                        </span>
                                      </td>
                                      <td className="p-2 text-slate-700 space-y-1">
                                        {Object.entries(rec.attributes || {}).map(([k, v], ki) => {
                                          const cits = rec.field_citations?.[k] || [];
                                          return (
                                            <div key={ki} className="flex items-center gap-1.5">
                                              <span className="font-semibold text-slate-600">{k}:</span>
                                              <span>{String(v)}</span>
                                              {cits.map((cl, cli) => (
                                                <button
                                                  key={cli}
                                                  type="button"
                                                  onClick={() => handleCitationClick(cl)}
                                                  className="text-[10px] font-mono text-sky-700 hover:underline"
                                                >
                                                  [{cl}]
                                                </button>
                                              ))}
                                            </div>
                                          );
                                        })}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}

                          {/* Missing Fields Notice */}
                          {deepExtract.missing_fields && deepExtract.missing_fields.length > 0 && (
                            <div className="p-2 bg-amber-50/70 border border-amber-200 rounded text-[10px] text-amber-900">
                              <span className="font-bold">Missing Fields in Evidence: </span>
                              {deepExtract.missing_fields.join(", ")}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Citation summary pills row */}
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center gap-1.5">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mr-1">
                            Citations:
                          </span>
                          {msg.citations.map((c, i) => (
                            <button
                              key={i}
                              type="button"
                              onClick={() => handleCitationClick(c.citation_label)}
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border transition ${
                                activeCitationLabel === c.citation_label
                                  ? "bg-emerald-600 text-white border-emerald-700 shadow-xs"
                                  : "bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100"
                              }`}
                              title={c.source_title}
                            >
                              <span>[{c.citation_label}]</span>
                              <span className="max-w-[120px] truncate">{c.source_provider}</span>
                            </button>
                          ))}
                          <span className="text-[10px] text-slate-400 italic ml-1">
                            (citations open source records)
                          </span>
                        </div>
                      )}

                      {/* INSUFFICIENT-EVIDENCE STATE ALERT (Zero Matches) */}
                      {isInsufficient && (
                        <div className="p-3 bg-amber-50/70 border border-dashed border-amber-300 rounded-lg text-amber-900 text-xs space-y-1">
                          <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[11px] text-amber-800">
                            <AlertCircle className="size-3.5 text-amber-600" />
                            INSUFFICIENT-EVIDENCE STATE
                          </div>
                          <p className="text-[11px] text-amber-800/90 leading-relaxed">
                            {msg.structured_payload_json?.uncertainty ||
                              "Available project evidence does not support a fully authoritative answer. Zero fabrication enforced."}
                          </p>
                          {msg.structured_payload_json?.missing_information &&
                            msg.structured_payload_json.missing_information.length > 0 && (
                              <div className="text-[10px] text-amber-700 mt-1 pl-4 list-disc">
                                {msg.structured_payload_json.missing_information.map((m, mi) => (
                                  <div key={mi}>• Missing context: {m}</div>
                                ))}
                              </div>
                            )}
                        </div>
                      )}

                      {/* PARTIAL EVIDENCE & UNCERTAINTY DISCLOSURE */}
                      {!isInsufficient && isPartial && (
                        <div className="p-3 bg-teal-50/50 border border-teal-200 rounded-lg text-teal-950 text-xs space-y-1">
                          <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[11px] text-teal-800">
                            <ShieldCheck className="size-3.5 text-teal-600" />
                            PARTIAL EVIDENCE &amp; CONTEXT DISCLOSURE
                          </div>
                          <p className="text-[11px] text-teal-900/90 leading-relaxed">
                            {msg.structured_payload_json?.uncertainty ||
                              "The answer above synthesizes available project records. Some detailed parameters or specific formulas remain unverified or missing from current sources."}
                          </p>
                          {msg.structured_payload_json?.missing_information &&
                            msg.structured_payload_json.missing_information.length > 0 && (
                              <div className="text-[10px] text-teal-800 mt-1 pl-4 list-disc">
                                {msg.structured_payload_json.missing_information.map((m, mi) => (
                                  <div key={mi}>• Missing context: {m}</div>
                                ))}
                              </div>
                            )}
                        </div>
                      )}

                      {/* CONFLICTS WARNING ALERT */}
                      {hasConflicts && (
                        <div className="p-3 bg-rose-50/70 border border-rose-200 rounded-lg text-rose-900 text-xs space-y-1">
                          <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[11px] text-rose-800">
                            <ShieldAlert className="size-3.5 text-rose-600" />
                            DETECTED CONFLICTS BETWEEN SOURCES
                          </div>
                          <div className="space-y-1 text-[11px] text-rose-800/90 pl-1">
                            {msg.structured_payload_json?.conflicts?.map((conf, ci) => (
                              <div key={ci} className="flex items-start gap-1">
                                <span>⚠️</span>
                                <span>{conf}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Factual Claims Accordion */}
                      {claims.length > 0 && (
                        <div className="pt-2 border-t border-slate-100">
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedClaims((prev) => ({ ...prev, [msg.id]: !prev[msg.id] }))
                            }
                            className="flex items-center justify-between w-full text-left text-[11px] font-semibold text-slate-600 hover:text-slate-900 py-1"
                          >
                            <span className="flex items-center gap-1.5">
                              <ShieldCheck className="size-3.5 text-teal-600" />
                              Factual Claims &amp; Confidence ({claims.length})
                            </span>
                            {isClaimsExpanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                          </button>

                          {isClaimsExpanded && (
                            <div className="mt-2 space-y-1.5 pl-2 border-l-2 border-teal-200">
                              {claims.map((claim, ci) => (
                                <div key={ci} className="p-2 bg-slate-50 rounded border border-slate-200 text-[11px]">
                                  <div className="text-slate-800 leading-snug">{claim.claim_text}</div>
                                  <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
                                    <div className="flex items-center gap-1">
                                      <span className="font-semibold text-emerald-700">
                                        {Math.round(claim.confidence * 100)}% conf
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-1 font-mono">
                                      {claim.citation_labels.map((cl, cli) => (
                                        <button
                                          key={cli}
                                          type="button"
                                          onClick={() => handleCitationClick(cl)}
                                          className="text-teal-700 hover:underline"
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

                      {/* Feedback Buttons */}
                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
                        <div className="text-[10px]">
                          Model: <span className="font-mono text-slate-600">{msg.model_name || "qwen3:8b"}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-400">Helpful?</span>
                          <button
                            type="button"
                            onClick={() => handleFeedback(msg.id, "helpful")}
                            disabled={Boolean(currentFeedback)}
                            className={`p-1 rounded hover:bg-slate-100 transition ${
                              currentFeedback === "helpful" ? "text-emerald-600 font-bold" : "text-slate-400"
                            }`}
                            title="Helpful response"
                          >
                            <ThumbsUp className="size-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleFeedback(msg.id, "unhelpful")}
                            disabled={Boolean(currentFeedback)}
                            className={`p-1 rounded hover:bg-slate-100 transition ${
                              currentFeedback === "unhelpful" ? "text-rose-600 font-bold" : "text-slate-400"
                            }`}
                            title="Needs improvement"
                          >
                            <ThumbsDown className="size-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* Suggested Follow-Up Questions */}
                      {followups.length > 0 && (
                        <div className="pt-2 border-t border-slate-100 space-y-1.5">
                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                            SUGGESTED FOLLOW-UP QUESTIONS
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {followups.map((fq, fi) => (
                              <button
                                key={fi}
                                type="button"
                                onClick={() => handleAsk(fq)}
                                disabled={asking}
                                className="px-2.5 py-1 text-[11px] rounded-full bg-slate-100 hover:bg-teal-50 hover:text-teal-900 border border-slate-200 hover:border-teal-300 text-slate-700 transition shadow-2xs text-left"
                              >
                                {fq}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {/* In-flight loading turn with live SSE progress & agent indicator */}
            {asking && (
              <div className="flex flex-col items-start w-full animate-fade-in space-y-2">
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500 uppercase font-semibold mb-1 ml-1">
                  <Bot className="size-3 text-teal-600 animate-spin" />
                  <span className="text-teal-900 font-bold">
                    {liveInvestigationStage === "initiating" && "INITIATING INVESTIGATION..."}
                    {liveInvestigationStage === "planning" && "QUERY PLANNING & SUBQUERY EXPANSION..."}
                    {liveInvestigationStage === "retrieving" && "HYBRID RETRIEVAL (CHROMADB + POSTGRESQL)..."}
                    {liveInvestigationStage === "delegating" && "DYNAMIC SPECIALIZED AGENT DELEGATION..."}
                    {liveInvestigationStage === "synthesizing" && "EVIDENCE SYNTHESIS (OLLAMA QWEN3 8B)..."}
                    {liveInvestigationStage === "streaming" && "STREAMING REAL-TIME ANSWER..."}
                    {!liveInvestigationStage && "REASONING & RETRIEVING..."}
                  </span>
                </div>
                <div className="w-full bg-white border border-teal-200 rounded-2xl rounded-tl-xs p-4 text-xs text-slate-600 shadow-xs flex flex-col gap-2.5">
                  <div className="flex items-center gap-2 text-teal-800 font-medium">
                    <Sparkles className="size-4 text-teal-600 animate-bounce shrink-0" />
                    <span>
                      {liveInvestigationEvents[liveInvestigationEvents.length - 1] ||
                        "Querying hybrid retrieval (ChromaDB + PostgreSQL) and synthesising with Ollama Qwen3 8B..."}
                    </span>
                  </div>

                  {/* Real-time streaming answer preview if available */}
                  {liveStreamingAnswer && (
                    <div className="mt-2 p-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 font-mono text-[11px] leading-relaxed max-h-40 overflow-y-auto whitespace-pre-wrap">
                      {liveStreamingAnswer}
                    </div>
                  )}

                  {/* Investigation activity breadcrumb stream */}
                  {liveInvestigationEvents.length > 1 && (
                    <div className="flex flex-wrap gap-1 mt-1 pt-2 border-t border-slate-100">
                      {liveInvestigationEvents.slice(-4).map((ev, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 text-[10px] bg-slate-100 text-slate-600 rounded-md border border-slate-200 flex items-center gap-1"
                        >
                          <CheckCircle2 className="size-2.5 text-teal-600" />
                          {ev}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Question Input Bar */}
          <div className="p-3 bg-white border-t border-slate-200 space-y-2">
            {/* Filter controls and Mode Selector row */}
            <div className="flex flex-wrap items-center justify-between text-xs gap-2 pt-1 pb-1">
              {/* Intelligent Mode Selector Tabs */}
              <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg">
                <button
                  type="button"
                  onClick={() => setResponseMode("standard")}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition ${
                    responseMode === "standard"
                      ? "bg-white text-teal-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                  title="Direct hybrid RAG answer with atomic citations"
                >
                  <Sparkles className="size-3 text-teal-600" />
                  <span>Standard</span>
                </button>
                <button
                  type="button"
                  onClick={() => setResponseMode("deep_research")}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition ${
                    responseMode === "deep_research"
                      ? "bg-white text-indigo-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                  title="Comprehensive multi-source research report with recommendations"
                >
                  <BookOpen className="size-3 text-indigo-600" />
                  <span>Deep Research</span>
                </button>
                <button
                  type="button"
                  onClick={() => setResponseMode("deep_think")}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition ${
                    responseMode === "deep_think"
                      ? "bg-white text-purple-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                  title="Causal and dependency reasoning with trade-offs"
                >
                  <Brain className="size-3 text-purple-600" />
                  <span>Deep Think</span>
                </button>
                <button
                  type="button"
                  onClick={() => setResponseMode("deep_extract")}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition ${
                    responseMode === "deep_extract"
                      ? "bg-white text-sky-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                  title="Structured schema extraction into tables with JSON export"
                >
                  <Table className="size-3 text-sky-600" />
                  <span>Deep Extract</span>
                </button>
              </div>

              {/* Domain & Search Mode Selectors */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase">Domain:</span>
                  <select
                    value={selectedDomain}
                    onChange={(e) => setSelectedDomain(e.target.value)}
                    className="text-[11px] bg-slate-50 border border-slate-200 rounded px-2 py-0.5 text-slate-700 focus:outline-hidden focus:ring-1 focus:ring-teal-500"
                  >
                    {DOMAINS_LIST.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase">Search:</span>
                  <select
                    value={retrievalMode}
                    onChange={(e) => setRetrievalMode(e.target.value as "hybrid" | "keyword" | "semantic")}
                    className="text-[11px] bg-slate-50 border border-slate-200 rounded px-2 py-0.5 text-slate-700 focus:outline-hidden focus:ring-1 focus:ring-teal-500"
                  >
                    <option value="hybrid">Hybrid (Vector + FTS)</option>
                    <option value="keyword">Keyword (FTS)</option>
                    <option value="semantic">Semantic (Vector)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Input field and send button */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAsk();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                placeholder="Ask a question about the project (e.g. architecture, ownership, decisions)..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                disabled={asking}
                className="flex-1 px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-900 placeholder-slate-400 transition"
              />
              <button
                type="submit"
                disabled={!inputValue.trim() || asking}
                className="px-4 py-2 bg-teal-700 hover:bg-teal-800 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition shadow-xs"
              >
                {asking ? <RefreshCw className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
                <span>Send</span>
              </button>
            </form>
          </div>
        </div>

        {/* ============================================================ */}
        {/* PANEL 3: RETRIEVED EVIDENCE (Right Panel)                    */}
        {/* ============================================================ */}
        <div className="lg:col-span-4 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[760px]">
          {/* Header */}
          <div className="bg-[#1e293b] text-white px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <FileText className="size-3.5 text-emerald-400" />
              3 RETRIEVED EVIDENCE
            </span>
            <span className="text-[11px] font-mono text-slate-300 bg-slate-800 px-2 py-0.5 rounded-full">
              {activeCitations.length} sources
            </span>
          </div>

          {/* Sub-tabs by category (Jira Tasks, GitHub Commits, Documents, Related Findings) */}
          <div className="flex border-b border-slate-200 bg-slate-50 px-2 pt-2 gap-1 overflow-x-auto text-xs">
            <button
              type="button"
              onClick={() => setEvidenceFilterTab("all")}
              className={`px-2.5 py-1.5 rounded-t-lg font-semibold border-t border-x text-[11px] whitespace-nowrap transition ${
                evidenceFilterTab === "all"
                  ? "bg-white border-slate-200 text-teal-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              All ({countsByProvider.all})
            </button>
            <button
              type="button"
              onClick={() => setEvidenceFilterTab("jira")}
              className={`px-2.5 py-1.5 rounded-t-lg font-semibold border-t border-x text-[11px] whitespace-nowrap transition ${
                evidenceFilterTab === "jira"
                  ? "bg-white border-slate-200 text-teal-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Jira Tasks ({countsByProvider.jira})
            </button>
            <button
              type="button"
              onClick={() => setEvidenceFilterTab("github")}
              className={`px-2.5 py-1.5 rounded-t-lg font-semibold border-t border-x text-[11px] whitespace-nowrap transition ${
                evidenceFilterTab === "github"
                  ? "bg-white border-slate-200 text-teal-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              GitHub ({countsByProvider.github})
            </button>
            <button
              type="button"
              onClick={() => setEvidenceFilterTab("documents")}
              className={`px-2.5 py-1.5 rounded-t-lg font-semibold border-t border-x text-[11px] whitespace-nowrap transition ${
                evidenceFilterTab === "documents"
                  ? "bg-white border-slate-200 text-teal-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Docs ({countsByProvider.documents})
            </button>
            <button
              type="button"
              onClick={() => setEvidenceFilterTab("findings")}
              className={`px-2.5 py-1.5 rounded-t-lg font-semibold border-t border-x text-[11px] whitespace-nowrap transition ${
                evidenceFilterTab === "findings"
                  ? "bg-white border-slate-200 text-teal-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Findings ({countsByProvider.findings})
            </button>
          </div>

          {/* Evidence Cards List */}
          <div className="flex-1 p-3.5 overflow-y-auto space-y-3">
            {filteredCitations.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center p-6 text-center text-slate-400">
                <Database className="size-8 text-slate-300 mb-2" />
                <div className="text-xs font-semibold text-slate-600">No Retrieved Evidence</div>
                <p className="text-[11px] text-slate-400 max-w-xs mt-1">
                  Ask a question in the center panel. Authorized supporting records will populate here with full provenance and direct quotations.
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
                    className={`p-3.5 rounded-xl border text-xs transition-all space-y-2.5 cursor-pointer ${
                      isSelected
                        ? "bg-emerald-50/50 border-emerald-500 ring-2 ring-emerald-500/30 shadow-xs"
                        : "bg-white border-slate-200 hover:border-slate-300 shadow-2xs"
                    }`}
                  >
                    {/* Top row: Label badge and Provider badge */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-600 text-white shadow-2xs">
                          [{citation.citation_label}]
                        </span>
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border ${
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
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <CheckCircle2 className="size-2.5 text-emerald-600" />
                          Human-Verified
                        </span>
                      )}
                    </div>

                    {/* Source Title */}
                    <div className="font-bold text-slate-900 text-xs leading-snug break-words">
                      {citation.source_title}
                    </div>

                    {/* Section or page info */}
                    {(citation.section_title || citation.page_number) && (
                      <div className="text-[10px] text-slate-500 font-medium">
                        {citation.section_title && <span>Section: {citation.section_title}</span>}
                        {citation.page_number && <span className="ml-1.5">· Page {citation.page_number}</span>}
                      </div>
                    )}

                    {/* Author & Timestamp */}
                    <div className="flex items-center gap-2 text-[10px] text-slate-400">
                      {citation.author && (
                        <span className="truncate">By: {citation.author}</span>
                      )}
                      {citation.source_timestamp && (
                        <>
                          <span>·</span>
                          <span>{new Date(citation.source_timestamp).toLocaleDateString()}</span>
                        </>
                      )}
                    </div>

                    {/* Direct Excerpt */}
                    <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-slate-700 text-[11px] italic leading-relaxed whitespace-pre-wrap">
                      &quot;{citation.excerpt}&quot;
                    </div>

                    {/* Action link */}
                    <div className="flex items-center justify-end pt-1">
                      {citation.source_url ? (
                        <a
                          href={citation.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[10px] font-semibold text-teal-700 hover:text-teal-900 hover:underline"
                        >
                          <span>Open Source Record</span>
                          <ExternalLink className="size-2.5" />
                        </a>
                      ) : (
                        <Link
                          href={`/evidence?id=${citation.evidence_id}`}
                          className="inline-flex items-center gap-1 text-[10px] font-semibold text-teal-700 hover:text-teal-900 hover:underline"
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
        </div>
      </div>
    </div>
  );
}
