import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType, MiniMap } from "reactflow";
import { AnalysisNode } from "./AnalysisNode.jsx";

const nodeTypes = {
  analysisNode: AnalysisNode,
};

const ACTIVE_EDGE_STYLE = {
  stroke: "rgba(94, 176, 255, 0.98)",
  strokeWidth: 2.5,
  filter: "drop-shadow(0 0 8px rgba(94, 176, 255, 0.42))",
};

const BASE_EDGE_STYLE = {
  stroke: "rgba(163, 179, 202, 0.68)",
  strokeWidth: 1.9,
  filter: "drop-shadow(0 0 4px rgba(56, 88, 132, 0.24))",
};

const MINIMAP_COLORS = {
  root: "#f6c455",
  class: "#b693ff",
  entrypoint: "#ff9a64",
  helper: "#4ed28d",
  function: "#6ab7ff",
  cluster: "#16e0c4",
};

const LEGEND_ITEMS = [
  { key: "root", label: "Root", color: MINIMAP_COLORS.root },
  { key: "entrypoint", label: "Entry", color: MINIMAP_COLORS.entrypoint },
  { key: "function", label: "Function", color: MINIMAP_COLORS.function },
  { key: "helper", label: "Helper", color: MINIMAP_COLORS.helper },
  { key: "class", label: "Class", color: MINIMAP_COLORS.class },
  { key: "cluster", label: "Cluster", color: MINIMAP_COLORS.cluster },
];

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

function GraphLegend({ hasSelection }) {
  return (
    <aside className="graph-legend" aria-hidden="true">
      <p className="graph-legend-title">Graph legend</p>
      <div className="graph-legend-grid">
        {LEGEND_ITEMS.map((item) => (
          <div key={item.key} className="graph-legend-item">
            <span className="graph-legend-mark" style={{ "--legend-color": item.color }} />
            <span>{item.label}</span>
          </div>
        ))}
      </div>
      <div className="graph-legend-status">
        <span className="graph-legend-status-label">Path highlight</span>
        <span className={`graph-legend-status-pill ${hasSelection ? "graph-legend-status-pill-active" : ""}`}>
          {hasSelection ? "On" : "Select a node"}
        </span>
      </div>
    </aside>
  );
}

export function GraphCanvas({ nodes, edges, selectedNodeId, onNodeSelect, onNodeToggleExpand, isLoading }) {
  const [flowInstance, setFlowInstance] = useState(null);
  const [miniMapVisible, setMiniMapVisible] = useState(false);

  const visibleChildCountByNode = useMemo(() => {
    const counts = new Map();
    for (const edge of edges) {
      counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1);
    }
    return counts;
  }, [edges]);

  const graphFocus = useMemo(() => {
    const parentByNode = new Map();
    const childEdgeIdsByNode = new Map();
    const edgeIdByPair = new Map();

    for (const edge of edges) {
      parentByNode.set(edge.target, edge.source);
      edgeIdByPair.set(`${edge.source}=>${edge.target}`, edge.id);
      if (!childEdgeIdsByNode.has(edge.source)) {
        childEdgeIdsByNode.set(edge.source, []);
      }
      childEdgeIdsByNode.get(edge.source).push(edge.id);
    }

    const pathNodeIds = new Set();
    const pathEdgeIds = new Set();
    const childNodeIds = new Set();

    if (selectedNodeId) {
      let current = selectedNodeId;
      while (current) {
        pathNodeIds.add(current);
        const parent = parentByNode.get(current);
        if (!parent) {
          break;
        }
        const edgeId = edgeIdByPair.get(`${parent}=>${current}`);
        if (edgeId) {
          pathEdgeIds.add(edgeId);
        }
        current = parent;
      }

      for (const edgeId of childEdgeIdsByNode.get(selectedNodeId) ?? []) {
        pathEdgeIds.add(edgeId);
      }

      for (const edge of edges) {
        if (edge.source === selectedNodeId) {
          childNodeIds.add(edge.target);
        }
      }
    }

    return {
      pathNodeIds,
      pathEdgeIds,
      childNodeIds,
    };
  }, [edges, selectedNodeId]);

  const decoratedNodes = useMemo(
    () =>
      nodes.map((node) => {
        const isSelected = node.id === selectedNodeId;
        const isPathNode = graphFocus.pathNodeIds.has(node.id);
        const isChildNode = graphFocus.childNodeIds.has(node.id);
        const depth = Number(node.data?.depth ?? 0);
        const role = String(node.data?.role ?? "function");
        const childCount = Number(node.data?.childCount ?? 0);
        const visibleChildCount = Number(visibleChildCountByNode.get(node.id) ?? 0);
        const hiddenChildCount = Math.max(0, childCount - visibleChildCount);
        const depthFade = Math.min(depth * 0.08, 0.3);
        const scale = isSelected ? 1.08 : depth === 0 ? 1.04 : depth === 1 ? 1.02 : 1;
        const baseOpacity = Math.max(0.72, 1 - depthFade);

        const roleBoost =
          role === "root" ? 0.08 : role === "class" ? 0.04 : role === "entrypoint" ? 0.05 : 0;

        return {
          ...node,
          selected: isSelected,
          data: {
            ...node.data,
            hiddenChildCount,
            canToggleExpand: childCount > 0,
            expanded: Boolean(node.data?.expanded),
            onToggleExpand:
              childCount > 0 && typeof onNodeToggleExpand === "function"
                ? () => onNodeToggleExpand(node.id)
                : undefined,
          },
          style: {
            ...node.style,
            opacity:
              selectedNodeId && !isSelected && !isPathNode && !isChildNode
                ? Math.max(0.46, baseOpacity - 0.28)
                : isSelected || isPathNode
                  ? Math.max(0.97, baseOpacity + roleBoost)
                  : Math.max(0.82, baseOpacity + roleBoost - 0.04),
            filter: isSelected
              ? "drop-shadow(0 0 28px rgba(94, 176, 255, 0.4))"
              : isPathNode
                ? "drop-shadow(0 0 22px rgba(94, 176, 255, 0.3))"
                : depth === 0
                ? "drop-shadow(0 0 20px rgba(246, 196, 85, 0.2))"
                : "none",
            "--node-scale": scale,
          },
        };
      }),
    [graphFocus.childNodeIds, graphFocus.pathNodeIds, nodes, onNodeToggleExpand, selectedNodeId, visibleChildCountByNode],
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
        const isActive = graphFocus.pathEdgeIds.has(edge.id);

        return {
          ...edge,
          animated: isActive,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 24,
            height: 24,
            color: isActive ? "rgba(94, 176, 255, 1)" : "rgba(163, 179, 202, 0.95)",
          },
          style: {
            ...BASE_EDGE_STYLE,
            ...(isActive ? ACTIVE_EDGE_STYLE : null),
            opacity: selectedNodeId && !isActive ? 0.34 : 0.94,
          },
        };
      }),
    [edges, graphFocus.pathEdgeIds, selectedNodeId],
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

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "m") {
        event.preventDefault();
        setMiniMapVisible((current) => !current);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

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
        onNodeDoubleClick={(_, node) => {
          if (typeof onNodeToggleExpand === "function") {
            onNodeToggleExpand(node.id);
          }
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
            color: "rgba(163, 179, 202, 0.95)",
          },
        }}
        proOptions={{
          hideAttribution: true,
        }}
      >
        <Controls />
        <div className="graph-minimap-shell">
          <button
            className="graph-minimap-toggle"
            type="button"
            onClick={() => setMiniMapVisible((current) => !current)}
            aria-label={miniMapVisible ? "Hide mini map" : "Show mini map"}
            aria-pressed={miniMapVisible}
            title={miniMapVisible ? "Hide mini map (Cmd/Ctrl+Shift+M)" : "Show mini map (Cmd/Ctrl+Shift+M)"}
          >
            <span aria-hidden="true">{miniMapVisible ? "‹" : "›"}</span>
          </button>
          {miniMapVisible ? (
            <MiniMap
              position="bottom-right"
              pannable
              zoomable
              ariaLabel="Graph mini map"
              nodeColor={(node) => MINIMAP_COLORS[String(node?.data?.role ?? "function")] ?? MINIMAP_COLORS.function}
              nodeStrokeColor={(node) =>
                graphFocus.pathNodeIds.has(node.id) ? "rgba(245, 251, 255, 0.98)" : "rgba(12, 20, 31, 0.9)"
              }
              nodeBorderRadius={8}
              nodeStrokeWidth={1.4}
              onNodeClick={(_, node) => {
                onNodeSelect(node.id);
              }}
              style={{
                background: "rgba(14, 22, 34, 0.94)",
                border: "1px solid rgba(186, 204, 228, 0.18)",
                borderRadius: "16px",
                boxShadow: "0 20px 46px rgba(0, 0, 0, 0.34)",
              }}
            />
          ) : null}
        </div>
        <GraphLegend hasSelection={Boolean(selectedNodeId)} />
        <Background gap={28} size={1.1} color="rgba(174, 194, 219, 0.18)" />
      </ReactFlow>
    </div>
  );
}
