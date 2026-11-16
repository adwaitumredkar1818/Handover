/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * src/web/topic/components/Diagram/Diagram.tsx
 * Original MIT License: Copyright (c) 2022 Joel Keyser
 */

"use client";

import React, { useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import {
  buildAmeliorateFlowchartElements,
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
  const { nodes: adaptedNodes, edges: adaptedEdges } = useMemo(
    () => buildAmeliorateFlowchartElements(rawNodes, rawEdges, selectedNodeId),
    [rawNodes, rawEdges, selectedNodeId]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<AmeliorateNodeData>>(adaptedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<AmeliorateEdgeData>>(adaptedEdges);

  useEffect(() => {
    setNodes(adaptedNodes);
    setEdges(adaptedEdges);
  }, [adaptedNodes, adaptedEdges, setNodes, setEdges]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => onSelectNode(node)}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.2}
      maxZoom={1.75}
    >
      <Background gap={18} size={1} color="#cbd5e1" />
      <Controls />
      <MiniMap
        nodeColor={(n) => {
          const data = n.data as AmeliorateNodeData | undefined;
          return data?.theme?.borderColor || "#315fba";
        }}
        maskColor="rgba(248, 250, 252, 0.72)"
      />
    </ReactFlow>
  );
}
