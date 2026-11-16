/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Edge/Edge.tsx & DirectEdge.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { memo } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import {
  AMELIORATE_DEFAULT_EDGE_COLOR,
  AMELIORATE_PRIMARY_SPOTLIGHT,
  type AmeliorateEdgeData,
} from "./ameliorateAdapter";

function AmeliorateFlowEdgeBase({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  markerEnd,
  data,
}: EdgeProps) {
  const edgeData = data as AmeliorateEdgeData | undefined;
  const isPrimary = edgeData?.spotlight === "primary";
  const isInferred = edgeData?.raw?.evidence_basis === "inferred";

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const stroke = isPrimary ? AMELIORATE_PRIMARY_SPOTLIGHT : AMELIORATE_DEFAULT_EDGE_COLOR;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke,
          strokeWidth: isPrimary ? 2 : 1.4,
          strokeDasharray: isInferred ? "5 4" : undefined,
          opacity: isPrimary ? 1 : 0.85,
        }}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "none",
              zIndex: isPrimary ? 10 : 1,
            }}
            className={`px-1 py-0.5 text-[10.5px] font-normal leading-none whitespace-nowrap rounded select-none ${
              isPrimary
                ? "bg-white/95 font-semibold text-indigo-600 shadow-xs"
                : "bg-white/80 text-slate-500"
            }`}
          >
            {String(label).toLowerCase()}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const AmeliorateFlowEdge = memo(AmeliorateFlowEdgeBase);
