"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { invalidateGraphCache } from "@/lib/graphCache";
import type { ProjectProcessingStatus } from "@/lib/types";

export function useProjectProcessingStatus(
  projectId: string,
  options?: {
    onProcessingComplete?: () => void;
  }
) {
  const [status, setStatus] = useState<ProjectProcessingStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [retrying, setRetrying] = useState<boolean>(false);
  const wasProcessingRef = useRef<boolean>(false);
  const lastGraphVersionRef = useRef<string | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const fetchStatus = useCallback(async () => {
    if (!projectId) return;
    try {
      const res = await api.projects.getProcessingStatus(projectId);
      setStatus(res);

      // Progressive graph update detection: invalidate graph cache whenever new knowledge/entities/relationships land
      if (res.graph_version && lastGraphVersionRef.current && res.graph_version !== lastGraphVersionRef.current) {
        invalidateGraphCache(`ki_graph:${projectId}:`);
        invalidateGraphCache(`ki_domains:${projectId}:`);
        invalidateGraphCache(`rel_contribs:${projectId}:`);
        invalidateGraphCache(`rel_entities:${projectId}:`);
        if (optionsRef.current?.onProcessingComplete) {
          optionsRef.current.onProcessingComplete();
        }
      }
      lastGraphVersionRef.current = res.graph_version ?? null;

      // Detect transition from processing -> ready/completed
      if (wasProcessingRef.current && !res.is_processing) {
        invalidateGraphCache(`ki_graph:${projectId}:`);
        invalidateGraphCache(`ki_domains:${projectId}:`);
        invalidateGraphCache(`rel_contribs:${projectId}:`);
        invalidateGraphCache(`rel_entities:${projectId}:`);
        if (optionsRef.current?.onProcessingComplete) {
          optionsRef.current.onProcessingComplete();
        }
      }
      wasProcessingRef.current = res.is_processing;
    } catch {
      // Ignore background status polling errors gracefully
    }
  }, [projectId]);

  const retry = useCallback(async () => {
    if (!projectId || retrying) return;
    setRetrying(true);
    try {
      const res = await api.projects.retryProcessing(projectId);
      setStatus(res);
      wasProcessingRef.current = res.is_processing;
    } catch {
      // Ignore
    } finally {
      setRetrying(false);
    }
  }, [projectId, retrying]);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    fetchStatus().finally(() => {
      if (isMounted) setLoading(false);
    });

    return () => {
      isMounted = false;
    };
  }, [fetchStatus]);

  // Dynamic polling: poll every 3s during active processing; poll every 15s when idle
  useEffect(() => {
    if (!projectId) return;

    const intervalMs = status?.is_processing ? 3000 : 15000;
    const interval = setInterval(() => {
      fetchStatus();
    }, intervalMs);

    return () => clearInterval(interval);
  }, [projectId, status?.is_processing, fetchStatus]);

  return {
    status,
    loading,
    retrying,
    isProcessing: Boolean(status?.is_processing),
    retry,
    refreshStatus: fetchStatus,
  };
}
