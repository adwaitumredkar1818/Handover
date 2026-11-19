import React from "react";
import { ErrorState } from "./ErrorState";
import { EmptyState } from "./EmptyState";
import { SectionLoader } from "./SectionLoader";

export interface LoadingBoundaryProps {
  isLoading: boolean;
  isError?: boolean;
  isEmpty?: boolean;
  error?: Error | string | null;
  skeleton?: React.ReactNode;
  emptyFallback?: React.ReactNode;
  errorFallback?: React.ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyActionLabel?: string;
  onEmptyAction?: () => void;
  onRetry?: () => void;
  children: React.ReactNode;
  className?: string;
}

export function LoadingBoundary({
  isLoading,
  isError = false,
  isEmpty = false,
  error,
  skeleton,
  emptyFallback,
  errorFallback,
  emptyTitle = "No records found",
  emptyDescription = "There is currently no data available for this view.",
  emptyActionLabel,
  onEmptyAction,
  onRetry,
  children,
  className = "",
}: LoadingBoundaryProps) {
  if (isLoading) {
    if (skeleton) return <>{skeleton}</>;
    return <SectionLoader className={className} />;
  }

  if (isError) {
    if (errorFallback) return <>{errorFallback}</>;
    return (
      <ErrorState
        message={error instanceof Error ? error.message : typeof error === "string" ? error : undefined}
        onRetry={onRetry}
        className={className}
      />
    );
  }

  if (isEmpty) {
    if (emptyFallback) return <>{emptyFallback}</>;
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        actionLabel={emptyActionLabel}
        onAction={onEmptyAction}
        className={className}
      />
    );
  }

  return <>{children}</>;
}

export default LoadingBoundary;
