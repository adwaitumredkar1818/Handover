import React from "react";

export interface TableSkeletonProps {
  rows?: number;
  columns?: number;
  showSearch?: boolean;
  className?: string;
}

export function TableSkeleton({
  rows = 5,
  columns = 5,
  showSearch = true,
  className = "",
}: TableSkeletonProps) {
  const rowList = Array.from({ length: rows }, (_, i) => i);
  const colList = Array.from({ length: columns }, (_, i) => i);

  return (
    <div
      className={`bg-white rounded-xl border border-[#DCE3EB] overflow-hidden shadow-2xs animate-pulse ${className}`}
      aria-hidden="true"
    >
      {/* Table Header / Action Bar */}
      {showSearch && (
        <div className="p-4 border-b border-[#DCE3EB] bg-[#F8FAFC] flex items-center justify-between gap-4">
          <div className="h-9 w-64 bg-[#E2E8F0] rounded-lg" />
          <div className="flex items-center gap-2">
            <div className="h-9 w-24 bg-[#E2E8F0] rounded-lg" />
            <div className="h-9 w-28 bg-[#CBD5E1] rounded-lg" />
          </div>
        </div>
      )}

      {/* Table Structure */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          {/* Table Column Headers */}
          <thead className="bg-[#F8FAFC] border-b border-[#DCE3EB]">
            <tr>
              {colList.map((c) => (
                <th key={c} className="py-3 px-4">
                  <div
                    className="h-3 bg-[#CBD5E1] rounded"
                    style={{ width: `${Math.max(40, (c + 1) * 22)}%` }}
                  />
                </th>
              ))}
            </tr>
          </thead>

          {/* Table Body Rows */}
          <tbody className="divide-y divide-[#F1F5F9]">
            {rowList.map((r) => (
              <tr key={r}>
                {colList.map((c) => (
                  <td key={c} className="py-3.5 px-4">
                    <div className="space-y-1.5">
                      <div
                        className="h-3 bg-[#E2E8F0] rounded"
                        style={{
                          width: `${Math.max(30, 85 - (c * 15 + (r % 3) * 10))}%`,
                        }}
                      />
                      {c === 0 && (
                        <div className="h-2 w-28 bg-[#F1F5F9] rounded" />
                      )}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default TableSkeleton;
