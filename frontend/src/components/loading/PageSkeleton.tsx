import React from "react";
import { CardSkeleton } from "./CardSkeleton";
import { TableSkeleton } from "./TableSkeleton";
import { ListSkeleton } from "./ListSkeleton";

export interface PageSkeletonProps {
  layout?: "dashboard" | "table" | "split" | "three-panel";
  className?: string;
}

export function PageSkeleton({
  layout = "dashboard",
  className = "",
}: PageSkeletonProps) {
  return (
    <div className={`space-y-6 animate-pulse ${className}`} aria-hidden="true">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#DCE3EB]">
        <div className="space-y-2">
          <div className="h-6 w-48 bg-[#CBD5E1] rounded-md" />
          <div className="h-3.5 w-72 bg-[#E2E8F0] rounded" />
        </div>
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-24 bg-[#E2E8F0] rounded-lg" />
          <div className="h-9 w-32 bg-[#315FBA]/30 rounded-lg" />
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <CardSkeleton variant="metric" count={4} />
      </div>

      {/* Body Layout */}
      {layout === "dashboard" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="p-6 bg-white rounded-xl border border-[#DCE3EB] space-y-4 shadow-2xs">
              <div className="flex items-center justify-between">
                <div className="h-4 w-40 bg-[#CBD5E1] rounded" />
                <div className="h-4 w-20 bg-[#E2E8F0] rounded" />
              </div>
              <div className="h-48 w-full bg-[#F8FAFC] rounded-lg flex items-center justify-center border border-[#E2E8F0]" />
            </div>
            <TableSkeleton rows={4} columns={4} showSearch={false} />
          </div>
          <div className="space-y-6">
            <div className="p-5 bg-white rounded-xl border border-[#DCE3EB] space-y-4 shadow-2xs">
              <div className="h-4 w-32 bg-[#CBD5E1] rounded" />
              <ListSkeleton variant="activity" count={4} />
            </div>
          </div>
        </div>
      )}

      {layout === "table" && (
        <TableSkeleton rows={8} columns={5} showSearch={true} />
      )}

      {layout === "split" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-4 p-5 bg-white rounded-xl border border-[#DCE3EB] space-y-4 shadow-2xs">
            <div className="h-4 w-32 bg-[#CBD5E1] rounded" />
            <ListSkeleton variant="thread" count={5} />
          </div>
          <div className="lg:col-span-8 p-6 bg-white rounded-xl border border-[#DCE3EB] space-y-5 shadow-2xs">
            <div className="h-5 w-52 bg-[#CBD5E1] rounded" />
            <div className="h-32 w-full bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]" />
            <div className="space-y-2">
              <div className="h-3.5 w-full bg-[#E2E8F0] rounded" />
              <div className="h-3.5 w-4/5 bg-[#E2E8F0] rounded" />
            </div>
          </div>
        </div>
      )}

      {layout === "three-panel" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[600px]">
          <div className="lg:col-span-3 p-4 bg-white rounded-xl border border-[#DCE3EB] space-y-4 shadow-2xs">
            <div className="h-4 w-28 bg-[#CBD5E1] rounded" />
            <ListSkeleton variant="source" count={3} />
          </div>
          <div className="lg:col-span-4 p-4 bg-white rounded-xl border border-[#DCE3EB] space-y-4 shadow-2xs">
            <div className="h-4 w-32 bg-[#CBD5E1] rounded" />
            <TableSkeleton rows={6} columns={2} showSearch={false} />
          </div>
          <div className="lg:col-span-5 p-5 bg-white rounded-xl border border-[#DCE3EB] space-y-4 shadow-2xs">
            <div className="h-5 w-48 bg-[#CBD5E1] rounded" />
            <div className="h-28 w-full bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]" />
          </div>
        </div>
      )}
    </div>
  );
}

export default PageSkeleton;
