import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Failed to load data",
  message = "An error occurred while fetching information from the server.",
  onRetry,
  className = "",
}: ErrorStateProps) {
  return (
    <div
      className={`p-6 bg-rose-50/60 rounded-xl border border-rose-200 text-center flex flex-col items-center justify-center space-y-3 ${className}`}
      role="alert"
    >
      <div className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
        <AlertCircle className="w-5 h-5 stroke-[2]" />
      </div>

      <div className="space-y-1">
        <h4 className="text-sm font-bold text-rose-900">{title}</h4>
        <p className="text-xs text-rose-700 max-w-md leading-relaxed">{message}</p>
      </div>

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-white border border-rose-300 text-xs font-semibold text-rose-800 hover:bg-rose-100 transition-colors shadow-2xs cursor-pointer mt-1"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Try Again</span>
        </button>
      )}
    </div>
  );
}

export default ErrorState;
