/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Diagram/Diagram.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { useEffect, useMemo, useRef, useCallback, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type ReactFlowInstance,
  type NodeChange,
  type Viewport,
} from "@xyflow/react";
import { Expand, Minimize2, LayoutGrid, Scan } from "lucide-react";
import {
  buildAmeliorateFlowchartElements,
  resolveIncrementalNodePositions,
  updateAmeliorateSpotlight,
  type AmeliorateEdgeData,
  type AmeliorateNodeData,
  type HandoverGraphEdge,
  type HandoverGraphNode,
} from "./ameliorateAdapter";
import { AmeliorateFlowNode } from "./AmeliorateFlowNode";
import { AmeliorateFlowEdge } from "./AmeliorateFlowEdge";

const nodeTypes = {
  ameliorateNode: AmeliorateFlowNode,
};

const edgeTypes = {
  ameliorateEdge: AmeliorateFlowEdge,
};

const FIT_VIEW_OPTIONS = { padding: 0.14, maxZoom: 1.05, minZoom: 0.2, duration: 240 };

export function AmeliorateFlowchartCanvas({
  rawNodes,
  rawEdges,
  selectedNodeId,
  onSelectNode,
}: {
  rawNodes: HandoverGraphNode[];
  rawEdges: HandoverGraphEdge[];
  selectedNodeId: string | null;
  onSelectNode: (node: Node) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [viewportSize, setViewportSize] = useState<{ width: number; height: number }>({
    width: 1100,
    height: 680,
  });
  const [layoutEpoch, setLayoutEpoch] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isOverlayFullscreen, setIsOverlayFullscreen] = useState(false);

  const positionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const measuredDimsRef = useRef<Map<string, { width: number; height: number }>>(new Map());
  const hasFittedRef = useRef(false);
  const savedViewportRef = useRef<Viewport | null>(null);
  const flowInstanceRef = useRef<ReactFlowInstance<
    Node<AmeliorateNodeData>,
    Edge<AmeliorateEdgeData>
  > | null>(null);

  // Measure container size with ResizeObserver for responsive adaptive layouts
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width < 100 || height < 100) return;

      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        setViewportSize((prev) => {
          if (Math.abs(prev.width - width) < 40 && Math.abs(prev.height - height) < 40) {
            return prev;
          }
          return { width: Math.round(width), height: Math.round(height) };
        });
      }, 120);
    });

    observer.observe(el);
    return () => {
      if (timer) clearTimeout(timer);
      observer.disconnect();
    };
  }, []);

  // Track native browser fullscreen state
  useEffect(() => {
    const handleFsChange = () => {
      const active = Boolean(document.fullscreenElement && document.fullscreenElement === containerRef.current);
      setIsFullscreen(active);
      if (!active && !isOverlayFullscreen && savedViewportRef.current && flowInstanceRef.current) {
        const vp = savedViewportRef.current;
        requestAnimationFrame(() => {
          flowInstanceRef.current?.setViewport(vp, { duration: 180 });
        });
      } else if (active && flowInstanceRef.current) {
        requestAnimationFrame(() => {
          flowInstanceRef.current?.fitView(FIT_VIEW_OPTIONS);
        });
      }
    };
    document.addEventListener("fullscreenchange", handleFsChange);
    return () => document.removeEventListener("fullscreenchange", handleFsChange);
  }, [isOverlayFullscreen]);

  // Escape key handler for overlay fullscreen fallback
  useEffect(() => {
    if (!isOverlayFullscreen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOverlayFullscreen(false);
        setIsFullscreen(false);
        if (savedViewportRef.current && flowInstanceRef.current) {
          const vp = savedViewportRef.current;
          requestAnimationFrame(() => {
            flowInstanceRef.current?.setViewport(vp, { duration: 180 });
          });
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOverlayFullscreen]);

  // 1. Topological & geometric layout computation (runs on raw data or explicit reorganise)
  const baseLayout = useMemo(
    () =>
      buildAmeliorateFlowchartElements(rawNodes, rawEdges, null, {
        viewportWidth: viewportSize.width,
        viewportHeight: viewportSize.height,
        nodeDimensions: measuredDimsRef.current,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rawNodes, rawEdges, layoutEpoch]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<AmeliorateNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<AmeliorateEdgeData>>([]);

  // Track position and measured dimension changes from React Flow
  const handleNodesChange = useCallback(
    (changes: NodeChange<Node<AmeliorateNodeData>>[]) => {
      onNodesChange(changes);
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          positionsRef.current.set(change.id, change.position);
        } else if (change.type === "dimensions" && change.dimensions) {
          measuredDimsRef.current.set(change.id, {
            width: change.dimensions.width,
            height: change.dimensions.height,
          });
        }
      }
    },
    [onNodesChange]
  );

  // On base layout change (initial load or progressive new nodes arriving),
  // preserve coordinates of previously positioned nodes and resolve local overlaps for new nodes only.
  useEffect(() => {
    const positionedNodes = resolveIncrementalNodePositions(
      baseLayout.nodes,
      baseLayout.edges,
      positionsRef.current,
      measuredDimsRef.current
    );

    const { nodes: updatedNodes, edges: updatedEdges } = updateAmeliorateSpotlight(
      positionedNodes,
      baseLayout.edges,
      selectedNodeId
    );
    setNodes(updatedNodes);
    setEdges(updatedEdges);

    if (!hasFittedRef.current && updatedNodes.length > 0 && flowInstanceRef.current) {
      hasFittedRef.current = true;
      requestAnimationFrame(() => {
        flowInstanceRef.current?.fitView({ ...FIT_VIEW_OPTIONS, duration: 0 });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseLayout, setNodes, setEdges]);

  // 2. Fast-path in-place spotlight update: ONLY runs on selection changes, leaving node coordinates & zoom untouched
  useEffect(() => {
    setNodes((currentNodes) =>
      updateAmeliorateSpotlight(currentNodes, edges, selectedNodeId).nodes
    );
    setEdges((currentEdges) =>
      updateAmeliorateSpotlight(nodes, currentEdges, selectedNodeId).edges
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId, setNodes, setEdges]);

  const onInit = useCallback(
    (
      instance: ReactFlowInstance<
        Node<AmeliorateNodeData>,
        Edge<AmeliorateEdgeData>
      >
    ) => {
      flowInstanceRef.current = instance;
      if (!hasFittedRef.current && nodes.length > 0) {
        hasFittedRef.current = true;
        requestAnimationFrame(() => {
          instance.fitView({ ...FIT_VIEW_OPTIONS, duration: 0 });
        });
      }
    },
    [nodes.length]
  );

  const handleFitView = useCallback(() => {
    flowInstanceRef.current?.fitView(FIT_VIEW_OPTIONS);
  }, []);

  const handleReorganiseLayout = useCallback(() => {
    positionsRef.current.clear();
    hasFittedRef.current = false;
    setLayoutEpoch((prev) => prev + 1);
  }, []);

  const handleToggleFullscreen = useCallback(async () => {
    const el = containerRef.current;
    if (!el) return;

    const currentlyExpanded = isFullscreen || isOverlayFullscreen;
    if (!currentlyExpanded) {
      if (flowInstanceRef.current) {
        savedViewportRef.current = flowInstanceRef.current.getViewport();
      }
      if (typeof el.requestFullscreen === "function") {
        try {
          await el.requestFullscreen();
          setIsFullscreen(true);
          return;
        } catch {
          // Fall back to application-level overlay fullscreen
        }
      }
      setIsOverlayFullscreen(true);
      setIsFullscreen(true);
      requestAnimationFrame(() => {
        flowInstanceRef.current?.fitView(FIT_VIEW_OPTIONS);
      });
    } else {
      if (document.fullscreenElement && typeof document.exitFullscreen === "function") {
        try {
          await document.exitFullscreen();
          return;
        } catch {
          // Fall back to closing overlay
        }
      }
      setIsOverlayFullscreen(false);
      setIsFullscreen(false);
      if (savedViewportRef.current && flowInstanceRef.current) {
        const vp = savedViewportRef.current;
        requestAnimationFrame(() => {
          flowInstanceRef.current?.setViewport(vp, { duration: 180 });
        });
      }
    }
  }, [isFullscreen, isOverlayFullscreen]);

  const expanded = isFullscreen || isOverlayFullscreen;

  return (
    <div
      ref={containerRef}
      className={
        isOverlayFullscreen
          ? "fixed inset-0 z-50 w-screen h-screen bg-slate-50 overflow-hidden"
          : "relative w-full h-full min-h-[420px] overflow-hidden bg-slate-50/40"
      }
      data-testid="ameliorate-graph-container"
    >
      {/* Top-right compact viewport & layout toolbar */}
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white/95 p-1 shadow-sm backdrop-blur-xs">
        <button
          type="button"
          onClick={handleFitView}
          title="Fit graph to view"
          aria-label="Fit graph to view"
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
        >
          <Scan className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Fit View</span>
        </button>
        <button
          type="button"
          onClick={handleReorganiseLayout}
          title="Reorganise layout"
          aria-label="Reorganise layout"
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
        >
          <LayoutGrid className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Reorganise</span>
        </button>
        <button
          type="button"
          onClick={handleToggleFullscreen}
          title={expanded ? "Exit fullscreen (Esc)" : "Expand to fullscreen"}
          aria-label={expanded ? "Exit fullscreen" : "Expand to fullscreen"}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
        >
          {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Expand className="h-3.5 w-3.5" />}
          <span className="hidden sm:inline">{expanded ? "Exit" : "Fullscreen"}</span>
        </button>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onSelectNode(node)}
        onInit={onInit}
        minZoom={0.15}
        maxZoom={2}
        fitViewOptions={FIT_VIEW_OPTIONS}
      >
        <Background gap={20} size={1.2} color="#cbd5e1" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          style={{ width: 164, height: 108 }}
          className="!rounded-xl !border !border-slate-200 !bg-white/95 !shadow-md"
          nodeColor={(n) => {
            const data = n.data as AmeliorateNodeData | undefined;
            return data?.theme?.borderColor || "#315fba";
          }}
          maskColor="rgba(15, 23, 42, 0.08)"
          nodeStrokeWidth={2}
        />
      </ReactFlow>
    </div>
  );
}
