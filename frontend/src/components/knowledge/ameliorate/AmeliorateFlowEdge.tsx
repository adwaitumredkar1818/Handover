/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Edge/Edge.tsx & DirectEdge.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { memo, useState } from "react";
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
  const [isHovered, setIsHovered] = useState(false);
  const edgeData = data as AmeliorateEdgeData | undefined;
  const isPrimary = edgeData?.spotlight === "primary";
  const isInferred = edgeData?.raw?.evidence_basis === "inferred";
  const hasCollision = edgeData?.hasCollision === true;
  const shouldShowLabel = Boolean(label) && (!hasCollision || isPrimary || isHovered);

  const [edgePath, defaultLabelX, defaultLabelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const finalLabelX = edgeData?.labelX ?? defaultLabelX;
  const finalLabelY = edgeData?.labelY ?? defaultLabelY;

  const stroke = isPrimary || isHovered ? AMELIORATE_PRIMARY_SPOTLIGHT : AMELIORATE_DEFAULT_EDGE_COLOR;
  const strokeWidth = isPrimary ? 2.2 : isHovered ? 2.0 : 1.4;

  return (
    <>
      {/* Invisible wider interaction path for effortless hover */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        className="cursor-pointer"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      />

      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke,
          strokeWidth,
          strokeDasharray: isInferred ? "5 4" : undefined,
          opacity: isPrimary || isHovered ? 1 : 0.85,
          transition: "stroke 0.15s ease, stroke-width 0.15s ease",
        }}
      />
      {shouldShowLabel && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${finalLabelX}px, ${finalLabelY}px)`,
              pointerEvents: "auto",
              zIndex: isPrimary || isHovered ? 40 : 10,
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            className={`px-2 py-0.5 text-[10.5px] font-medium leading-none whitespace-nowrap rounded-md select-none border transition-all ${
              isPrimary || isHovered
                ? "bg-indigo-50 border-indigo-400 text-indigo-700 font-semibold shadow-md ring-1 ring-indigo-200"
                : "bg-white border-slate-300 text-slate-700 shadow-2xs"
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
