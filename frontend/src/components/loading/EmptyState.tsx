import React from "react";
import { FolderOpen, Plus } from "lucide-react";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 text-center bg-white rounded-xl border border-dashed border-[#DCE3EB] select-none ${className}`}
    >
      <div className="w-12 h-12 rounded-2xl bg-[#F0F4F9] text-[#4774A9] flex items-center justify-center mb-3 shadow-2xs">
        {icon || <FolderOpen className="w-6 h-6 stroke-[1.6]" />}
      </div>
      <h3 className="text-sm font-bold text-[#203653] tracking-tight">{title}</h3>
      <p className="text-xs text-[#69778D] max-w-sm mt-1 leading-relaxed">
        {description}
      </p>

      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-[#315FBA] hover:bg-[#254A94] text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{actionLabel}</span>
        </button>
      )}
    </div>
  );
}

export default EmptyState;
