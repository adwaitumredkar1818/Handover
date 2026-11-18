/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Diagram/Diagram.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { useEffect, useMemo, useRef, useCallback } from "react";
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
} from "@xyflow/react";
import {
  buildAmeliorateFlowchartElements,
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
  // 1. Heavy topological & geometric layout computation ONLY runs when raw data changes
  const baseLayout = useMemo(
    () => buildAmeliorateFlowchartElements(rawNodes, rawEdges, null),
    [rawNodes, rawEdges]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<AmeliorateNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<AmeliorateEdgeData>>([]);

  const positionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const hasFittedRef = useRef(false);
  const flowInstanceRef = useRef<ReactFlowInstance<
    Node<AmeliorateNodeData>,
    Edge<AmeliorateEdgeData>
  > | null>(null);

  // Track position changes when user drags nodes so live updates respect user placement
  const handleNodesChange = useCallback(
    (changes: NodeChange<Node<AmeliorateNodeData>>[]) => {
      onNodesChange(changes);
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          positionsRef.current.set(change.id, change.position);
        }
      }
    },
    [onNodesChange]
  );

  // On base layout change (initial load or progressive new nodes arriving),
  // preserve coordinates of previously positioned nodes to eliminate camera jumps.
  useEffect(() => {
    const preservedNodes = baseLayout.nodes.map((newNode) => {
      const existingPos = positionsRef.current.get(newNode.id);
      if (existingPos) {
        return { ...newNode, position: existingPos };
      }
      positionsRef.current.set(newNode.id, newNode.position);
      return newNode;
    });

    const { nodes: updatedNodes, edges: updatedEdges } = updateAmeliorateSpotlight(
      preservedNodes,
      baseLayout.edges,
      selectedNodeId
    );
    setNodes(updatedNodes);
    setEdges(updatedEdges);

    // Initial camera fit once when first nodes arrive
    if (!hasFittedRef.current && updatedNodes.length > 0 && flowInstanceRef.current) {
      flowInstanceRef.current.fitView({ padding: 0.15, maxZoom: 1.1, minZoom: 0.4 });
      hasFittedRef.current = true;
    }
  }, [baseLayout, setNodes, setEdges]);

  // 2. Fast-path in-place spotlight update: ONLY runs on selection changes, leaving node coordinates untouched
  useEffect(() => {
    setNodes((currentNodes) =>
      updateAmeliorateSpotlight(currentNodes, edges, selectedNodeId).nodes
    );
    setEdges((currentEdges) =>
      updateAmeliorateSpotlight(nodes, currentEdges, selectedNodeId).edges
    );
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
      instance.fitView({ padding: 0.15, maxZoom: 1.1, minZoom: 0.4 });
      hasFittedRef.current = true;
    }
  }, [nodes.length]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={handleNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => onSelectNode(node)}
      onInit={onInit}
    >
      <Background gap={20} size={1.2} color="#cbd5e1" />
      <Controls />
      <MiniMap
        nodeColor={(n) => {
          const data = n.data as AmeliorateNodeData | undefined;
          return data?.theme?.borderColor || "#315fba";
        }}
        maskColor="rgba(248, 250, 252, 0.75)"
      />
    </ReactFlow>
  );
}
