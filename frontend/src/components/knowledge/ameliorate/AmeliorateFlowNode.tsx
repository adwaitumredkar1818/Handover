/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Node/EditableNode.tsx & FlowNode.tsx & NodeHandle.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  CheckCircle2,
  ClipboardList,
  Cpu,
  Database,
  FileCheck2,
  FileText,
  FolderGit2,
  GitCommitHorizontal,
  GitPullRequest,
  Layers,
  Workflow,
} from "lucide-react";
import {
  AMELIORATE_PRIMARY_SPOTLIGHT,
  AMELIORATE_SECONDARY_SPOTLIGHT,
  type AmeliorateNodeData,
  type AmeliorateNodeTheme,
} from "./ameliorateAdapter";

function NodeTypeIcon({ iconKey }: { iconKey: AmeliorateNodeTheme["iconKey"] }) {
  const cls = "size-3 shrink-0 text-slate-900";
  switch (iconKey) {
    case "project":
      return <FolderGit2 className={cls} />;
    case "feature":
      return <Workflow className={cls} />;
    case "requirement":
      return <FileCheck2 className={cls} />;
    case "workflow":
      return <Layers className={cls} />;
    case "work_item":
      return <ClipboardList className={cls} />;
    case "component":
      return <Cpu className={cls} />;
    case "technology":
      return <Cpu className={cls} />;
    case "database":
      return <Database className={cls} />;
    case "document":
      return <FileText className={cls} />;
    case "pull_request":
      return <GitPullRequest className={cls} />;
    case "commit":
      return <GitCommitHorizontal className={cls} />;
    default:
      return <Workflow className={cls} />;
  }
}

function AmeliorateFlowNodeBase({ data, selected }: NodeProps) {
  const { raw, theme, spotlight } = data as AmeliorateNodeData;
  const isPrimary = selected || spotlight === "primary";
  const isSecondary = !isPrimary && spotlight === "secondary";

  const borderColor = isPrimary
    ? AMELIORATE_PRIMARY_SPOTLIGHT
    : isSecondary
      ? AMELIORATE_SECONDARY_SPOTLIGHT
      : theme.borderColor;

  const isVerified = raw.verification_status === "approved";

  return (
    <div
      className="group relative flex w-[184px] flex-col rounded-md border-[1.5px] bg-white shadow-xs transition-shadow pointer-events-auto cursor-pointer select-none"
      style={{
        borderColor,
        boxShadow: isPrimary
          ? `0 0 0 2px ${AMELIORATE_PRIMARY_SPOTLIGHT}33, 0 4px 12px rgba(15, 23, 42, 0.12)`
          : isSecondary
            ? `0 0 0 1px ${AMELIORATE_SECONDARY_SPOTLIGHT}44, 0 2px 6px rgba(15, 23, 42, 0.08)`
            : "0 1px 2px rgba(15, 23, 42, 0.06)",
      }}
    >
      {/* 4-side Ameliorate connection handles */}
      <Handle
        id="top"
        type="target"
        position={Position.Top}
        className="!size-2 !bg-slate-400 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
      />
      <Handle
        id="bottom"
        type="source"
        position={Position.Bottom}
        className="!size-2 !bg-slate-400 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
      />
      <Handle
        id="left"
        type="target"
        position={Position.Left}
        className="!size-2 !bg-slate-400 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
      />
      <Handle
        id="right"
        type="source"
        position={Position.Right}
        className="!size-2 !bg-slate-400 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
      />

      {/* Top row: Ameliorate colored top-left badge with dark text & icon */}
      <div className="flex h-6 items-center justify-between">
        <div
          className="flex h-6 items-center gap-1 rounded-tl-[4px] rounded-br-[6px] px-2 text-[11px] font-medium text-slate-900 leading-none"
          style={{ backgroundColor: theme.badgeBg }}
        >
          <NodeTypeIcon iconKey={theme.iconKey} />
          <span className="truncate max-w-[116px]">{theme.typeLabel}</span>
        </div>

        {isVerified && (
          <span title="Human Verified" className="pr-1.5 text-emerald-600">
            <CheckCircle2 className="size-3.5" />
          </span>
        )}
      </div>

      {/* Middle body: centered Ameliorate node text */}
      <div className="flex items-center justify-center px-3 pt-2 pb-3 min-h-[42px]">
        <p className="text-[12.5px] font-medium leading-snug text-slate-900 text-center line-clamp-2">
          {raw.label}
        </p>
      </div>
    </div>
  );
}

export const AmeliorateFlowNode = memo(AmeliorateFlowNodeBase);
