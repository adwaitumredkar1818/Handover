import React from "react";
import { CheckCircle2, ArrowRight } from "lucide-react";

export interface SuccessStateProps {
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function SuccessState({
  title,
  message,
  actionLabel,
  onAction,
  className = "",
}: SuccessStateProps) {
  return (
    <div
      className={`p-6 bg-teal-50/60 rounded-xl border border-teal-200 text-center flex flex-col items-center justify-center space-y-3 ${className}`}
      role="status"
    >
      <div className="w-10 h-10 rounded-full bg-teal-100 text-[#299B80] flex items-center justify-center shrink-0">
        <CheckCircle2 className="w-6 h-6 stroke-[2]" />
      </div>

      <div className="space-y-1">
        <h4 className="text-sm font-bold text-teal-950">{title}</h4>
        {message && (
          <p className="text-xs text-teal-800 max-w-md leading-relaxed">{message}</p>
        )}
      </div>

      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#299B80] text-white text-xs font-semibold hover:bg-[#1E7762] transition-colors shadow-2xs cursor-pointer mt-1"
        >
          <span>{actionLabel}</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

export default SuccessState;
