import React from "react";

export interface FormSkeletonProps {
  fields?: number;
  className?: string;
}

export function FormSkeleton({ fields = 4, className = "" }: FormSkeletonProps) {
  const items = Array.from({ length: fields }, (_, i) => i);

  return (
    <div
      className={`p-6 bg-white rounded-xl border border-[#DCE3EB] space-y-5 animate-pulse ${className}`}
      aria-hidden="true"
    >
      {/* Form Header */}
      <div className="space-y-1.5 pb-4 border-b border-[#F1F5F9]">
        <div className="h-4 w-48 bg-[#CBD5E1] rounded" />
        <div className="h-3 w-80 bg-[#E2E8F0] rounded" />
      </div>

      {/* Field Items */}
      <div className="space-y-4">
        {items.map((i) => (
          <div key={i} className="space-y-1.5">
            <div className="h-3 w-32 bg-[#CBD5E1] rounded" />
            <div className="h-9 w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg" />
            {i % 2 === 1 && <div className="h-2 w-48 bg-[#F1F5F9] rounded" />}
          </div>
        ))}
      </div>

      {/* Form Actions */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#F1F5F9]">
        <div className="h-9 w-20 bg-[#E2E8F0] rounded-lg" />
        <div className="h-9 w-28 bg-[#CBD5E1] rounded-lg" />
      </div>
    </div>
  );
}

export default FormSkeleton;
