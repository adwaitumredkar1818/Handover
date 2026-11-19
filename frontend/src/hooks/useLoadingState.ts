import { useState, useCallback, useRef, useEffect } from "react";

export type AsyncOperationStatus =
  | "idle"
  | "initializing"
  | "loading"
  | "processing"
  | "uploading"
  | "refreshing"
  | "success"
  | "empty"
  | "error"
  | "cancelled";

export interface LoadingStateControls<T = unknown> {
  status: AsyncOperationStatus;
  isLoading: boolean;
  isSuccess: boolean;
  isError: boolean;
  isIdle: boolean;
  error: Error | string | null;
  data: T | null;
  startLoading: (customStatus?: AsyncOperationStatus) => void;
  setSuccess: (resolvedData?: T | null) => void;
  setError: (err: Error | string) => void;
  setEmpty: () => void;
  reset: () => void;
  cancel: () => void;
}

export function useLoadingState<T = unknown>(
  initialStatus: AsyncOperationStatus = "idle",
  initialData: T | null = null
): LoadingStateControls<T> {
  const [status, setStatus] = useState<AsyncOperationStatus>(initialStatus);
  const [error, setErr] = useState<Error | string | null>(null);
  const [data, setData] = useState<T | null>(initialData);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const startLoading = useCallback((customStatus: AsyncOperationStatus = "loading") => {
    if (!isMountedRef.current) return;
    setStatus(customStatus);
    setErr(null);
  }, []);

  const setSuccess = useCallback((resolvedData?: T | null) => {
    if (!isMountedRef.current) return;
    setStatus("success");
    setErr(null);
    if (resolvedData !== undefined) {
      setData(resolvedData);
    }
  }, []);

  const setError = useCallback((err: Error | string) => {
    if (!isMountedRef.current) return;
    setStatus("error");
    setErr(err);
  }, []);

  const setEmpty = useCallback(() => {
    if (!isMountedRef.current) return;
    setStatus("empty");
    setErr(null);
  }, []);

  const reset = useCallback(() => {
    if (!isMountedRef.current) return;
    setStatus(initialStatus);
    setErr(null);
    setData(initialData);
  }, [initialStatus, initialData]);

  const cancel = useCallback(() => {
    if (!isMountedRef.current) return;
    setStatus("cancelled");
  }, []);

  const isLoading =
    status === "loading" ||
    status === "initializing" ||
    status === "processing" ||
    status === "uploading" ||
    status === "refreshing";

  return {
    status,
    isLoading,
    isSuccess: status === "success",
    isError: status === "error",
    isIdle: status === "idle",
    error,
    data,
    startLoading,
    setSuccess,
    setError,
    setEmpty,
    reset,
    cancel,
  };
}
