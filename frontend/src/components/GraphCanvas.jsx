import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import { AnalysisNode } from "./AnalysisNode.jsx";

const nodeTypes = {
  analysisNode: AnalysisNode,
};

const ACTIVE_EDGE_STYLE = {
  stroke: "rgba(104, 166, 255, 0.95)",
  strokeWidth: 2.4,
  filter: "drop-shadow(0 0 6px rgba(104, 166, 255, 0.35))",
};

const BASE_EDGE_STYLE = {
  stroke: "rgba(148, 163, 184, 0.42)",
  strokeWidth: 1.85,
  filter: "drop-shadow(0 0 4px rgba(104, 166, 255, 0.14))",
};

function EmptyState({ isLoading }) {
  return (
    <div className="graph-empty">
      <div className="graph-empty-card">
        <p className="graph-empty-kicker">{isLoading ? "Generating graph" : "Ready when you are"}</p>
        <h3>{isLoading ? "Building the call graph..." : "Analyze a project path to start."}</h3>
        <p>
          {isLoading
            ? "We are laying out the tree and preparing the React Flow canvas."
            : "Enter a local project path above, then click Analyze to render the graph."}
        </p>
      </div>
    </div>
  );
}

export function GraphCanvas({ nodes, edges, selectedNodeId, onNodeSelect, isLoading }) {
  const [flowInstance, setFlowInstance] = useState(null);

  const connectedEdgeIds = useMemo(() => {
    if (!selectedNodeId) {
      return new Set();
    }

    return new Set(
      edges
        .filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId)
        .map((edge) => edge.id),
    );
  }, [edges, selectedNodeId]);

  const decoratedNodes = useMemo(
    () =>
      nodes.map((node) => {
        const isSelected = node.id === selectedNodeId;
        const depth = Number(node.data?.depth ?? 0);
        const role = String(node.data?.role ?? "function");
        const depthFade = Math.min(depth * 0.08, 0.3);
        const scale = isSelected ? 1.08 : depth === 0 ? 1.04 : depth === 1 ? 1.02 : 1;
        const baseOpacity = Math.max(0.72, 1 - depthFade);

        const roleBoost =
          role === "root" ? 0.08 : role === "class" ? 0.04 : role === "entrypoint" ? 0.05 : 0;

        return {
          ...node,
          selected: isSelected,
          style: {
            ...node.style,
            opacity: selectedNodeId && !isSelected ? Math.max(0.44, baseOpacity - 0.16) : baseOpacity + roleBoost,
            filter: isSelected
              ? "drop-shadow(0 0 24px rgba(96, 165, 250, 0.35))"
              : depth === 0
                ? "drop-shadow(0 0 18px rgba(250, 204, 21, 0.18))"
                : "none",
            "--node-scale": scale,
          },
        };
      }),
    [nodes, selectedNodeId],
  );

  function focusNode(nodeId) {
    if (!flowInstance) {
      return;
    }

    const runtimeNode = flowInstance.getNode?.(nodeId);
    if (!runtimeNode) {
      return;
    }

    const position = runtimeNode.positionAbsolute ?? runtimeNode.position ?? { x: 0, y: 0 };
    const width = runtimeNode.width ?? runtimeNode.measured?.width ?? runtimeNode.style?.width ?? 240;
    const height = runtimeNode.height ?? runtimeNode.measured?.height ?? runtimeNode.style?.height ?? 116;
    const centerX = position.x + width / 2;
    const centerY = position.y + height / 2;
    const zoom = runtimeNode.data?.role === "root" ? 1.05 : runtimeNode.data?.childCount >= 4 ? 1.2 : 1.28;

    flowInstance.setCenter(centerX, centerY, {
      zoom,
      duration: 520,
    });
  }

  const decoratedEdges = useMemo(
    () =>
      edges.map((edge) => {
        const isActive = connectedEdgeIds.has(edge.id);

        return {
          ...edge,
          animated: isActive,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 24,
            height: 24,
            color: isActive ? "rgba(104, 166, 255, 1)" : "rgba(148, 163, 184, 0.82)",
          },
          style: {
            ...BASE_EDGE_STYLE,
            ...(isActive ? ACTIVE_EDGE_STYLE : null),
            opacity: selectedNodeId && !isActive ? 0.18 : 0.9,
          },
        };
      }),
    [connectedEdgeIds, edges, selectedNodeId],
  );

  useEffect(() => {
    if (!flowInstance || nodes.length === 0) {
      return undefined;
    }

    const frame = window.requestAnimationFrame(() => {
      flowInstance.fitView({
        padding: 0.2,
        duration: 500,
        minZoom: 0.28,
        maxZoom: 1.45,
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [flowInstance, nodes.length, edges.length]);

  useEffect(() => {
    if (!selectedNodeId || !flowInstance) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      focusNode(selectedNodeId);
    });

    return () => window.cancelAnimationFrame(frame);
  }, [flowInstance, selectedNodeId]);

  if (nodes.length === 0) {
    return <EmptyState isLoading={isLoading} />;
  }

  return (
    <div className="graph-canvas">
      <ReactFlow
        nodes={decoratedNodes}
        edges={decoratedEdges}
        nodeTypes={nodeTypes}
        onInit={setFlowInstance}
        onNodeClick={(_, node) => {
          onNodeSelect(node.id);
          focusNode(node.id);
        }}
        fitView
        minZoom={0.25}
        maxZoom={1.75}
        nodesDraggable={false}
        nodesConnectable={false}
        panOnScroll
        zoomOnScroll
        zoomOnPinch
        panOnDrag
        defaultEdgeOptions={{
          type: "bezier",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 24,
            height: 24,
            color: "rgba(148, 163, 184, 0.82)",
          },
        }}
        proOptions={{
          hideAttribution: true,
        }}
      >
        <Controls />
        <Background gap={26} size={1} color="rgba(148, 163, 184, 0.12)" />
      </ReactFlow>
    </div>
  );
}
