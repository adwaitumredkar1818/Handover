/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Node/EditableNode.tsx & FlowNode.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { CheckCircle2 } from "lucide-react";
import {
  AMELIORATE_PRIMARY_SPOTLIGHT,
  AMELIORATE_SECONDARY_SPOTLIGHT,
  type AmeliorateNodeData,
} from "./ameliorateAdapter";

function AmeliorateFlowNodeBase({ data, selected }: NodeProps) {
  const { raw, theme, spotlight } = data as AmeliorateNodeData;
  const isPrimary = selected || spotlight === "primary";
  const isSecondary = !isPrimary && spotlight === "secondary";

  const borderColor = isPrimary
    ? AMELIORATE_PRIMARY_SPOTLIGHT
    : isSecondary
      ? AMELIORATE_SECONDARY_SPOTLIGHT
      : theme.borderColor;

  const isVerified =
    raw.verification_status === "approved" ||
    raw.status === "HUMAN_VERIFIED" ||
    raw.status === "verified_implementation";

  return (
    <div
      className="group relative flex w-[204px] min-h-[68px] flex-col rounded-lg border-2 bg-white shadow-xs transition-all pointer-events-auto cursor-pointer select-none"
      style={{
        borderColor,
        boxShadow: isPrimary
          ? `0 0 0 2px ${AMELIORATE_PRIMARY_SPOTLIGHT}33, 0 4px 12px rgba(15, 23, 42, 0.12)`
          : isSecondary
            ? `0 0 0 1px ${AMELIORATE_SECONDARY_SPOTLIGHT}44, 0 2px 6px rgba(15, 23, 42, 0.08)`
            : "0 1px 3px rgba(15, 23, 42, 0.06)",
      }}
    >
      {/* Top Target Handle */}
      <Handle
        id="top"
        type="target"
        position={Position.Top}
        className="!size-2 !bg-slate-400 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
      />

      {/* Bottom Source Handle */}
      <Handle
        id="bottom"
        type="source"
        position={Position.Bottom}
        className="!size-2 !bg-slate-400 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
      />

      {/* Top row: Ameliorate colored top-left badge flush to top-left */}
      <div className="flex h-5 items-center justify-between">
        <div
          className="flex h-5 items-center gap-1 rounded-tl-[6px] rounded-br-[6px] px-2 text-[11px] font-semibold leading-none"
          style={{ backgroundColor: theme.badgeBg, color: theme.badgeText }}
        >
          <span>{theme.iconSymbol}</span>
          <span className="truncate max-w-[124px]">{theme.typeLabel}</span>
        </div>

        {isVerified && (
          <span title="Human Verified" className="pr-1.5 text-emerald-600">
            <CheckCircle2 className="size-3.5" />
          </span>
        )}
      </div>

      {/* Middle body: clean centered Ameliorate node text */}
      <div className="flex flex-1 items-center justify-center px-3 py-2">
        <p className="text-[13px] font-medium leading-snug text-slate-800 text-center line-clamp-2">
          {raw.label}
        </p>
      </div>
    </div>
  );
}

export const AmeliorateFlowNode = memo(AmeliorateFlowNodeBase);
