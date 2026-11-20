import { useState, useCallback, useRef, useEffect } from "react";
import { useLoadingState, type AsyncOperationStatus } from "./useLoadingState";

export interface OperationStatusOptions<T> {
  onSuccess?: (data: T) => void;
  onError?: (error: Error | string) => void;
  timeoutMs?: number;
  initialStatus?: AsyncOperationStatus;
}

export function useOperationStatus<T = unknown, P extends unknown[] = unknown[]>(
  operation: (...args: P) => Promise<T>,
  options: OperationStatusOptions<T> = {}
) {
  const { onSuccess, onError, timeoutMs, initialStatus = "idle" } = options;
  const loading = useLoadingState<T>(initialStatus);
  const [retries, setRetries] = useState(0);
  const lastArgsRef = useRef<P | null>(null);
  const timeoutIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
      }
    };
  }, []);

  const execute = useCallback(
    async (...args: P): Promise<T | null> => {
      lastArgsRef.current = args;
      loading.startLoading();

      if (timeoutMs) {
        if (timeoutIdRef.current) clearTimeout(timeoutIdRef.current);
        timeoutIdRef.current = setTimeout(() => {
          loading.setError(new Error(`Operation timed out after ${timeoutMs}ms`));
          onError?.(`Operation timed out after ${timeoutMs}ms`);
        }, timeoutMs);
      }

      try {
        const result = await operation(...args);
        if (timeoutIdRef.current) clearTimeout(timeoutIdRef.current);
        loading.setSuccess(result);
        onSuccess?.(result);
        return result;
      } catch (err: unknown) {
        if (timeoutIdRef.current) clearTimeout(timeoutIdRef.current);
        const errorObj = err instanceof Error ? err : new Error(String(err));
        loading.setError(errorObj);
        onError?.(errorObj);
        return null;
      }
    },
    [operation, loading, timeoutMs, onSuccess, onError]
  );

  const retry = useCallback(() => {
    if (lastArgsRef.current) {
      setRetries((prev) => prev + 1);
      return execute(...lastArgsRef.current);
    }
    return Promise.resolve(null);
  }, [execute]);

  return {
    ...loading,
    execute,
    retry,
    retries,
  };
}
