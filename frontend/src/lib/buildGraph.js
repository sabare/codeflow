const HORIZONTAL_GAP = 72;
const LEVEL_GAP = 124;
const TOP_PADDING = 96;
const LEFT_PADDING = 96;
const DEFAULT_DEPTH = 1;

const ROLE_META = {
  root: {
    label: "root",
    accent: "root",
    glyph: "◉",
    width: 290,
    height: 136,
  },
  class: {
    label: "class",
    accent: "class",
    glyph: "⬡",
    width: 258,
    height: 124,
  },
  entrypoint: {
    label: "entrypoint",
    accent: "entrypoint",
    glyph: "◆",
    width: 254,
    height: 120,
  },
  function: {
    label: "function",
    accent: "function",
    glyph: "●",
    width: 240,
    height: 116,
  },
  helper: {
    label: "helper",
    accent: "helper",
    glyph: "↳",
    width: 228,
    height: 110,
  },
  cluster: {
    label: "cluster",
    accent: "cluster",
    glyph: "◌",
    width: 272,
    height: 126,
  },
};

const ROLE_WEIGHT = {
  root: 0,
  entrypoint: 1,
  function: 2,
  class: 3,
  helper: 4,
  cluster: 5,
};

function normalizeList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))];
}

function slugify(value) {
  return (
    String(value ?? "node")
      .trim()
      .toLowerCase()
      .replace(/['"]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "node"
  );
}

function edgeKey(source, target) {
  return `${source}=>${target}`;
}

function getNodeSize(role) {
  const meta = ROLE_META[role] ?? ROLE_META.function;
  return {
    width: meta.width,
    height: meta.height,
  };
}

function inferRole(roleHint, name, depth, childCount) {
  const normalizedHint = String(roleHint ?? "").trim().toLowerCase();
  if (normalizedHint && ROLE_META[normalizedHint]) {
    return normalizedHint;
  }

  if (depth === 0) {
    return "root";
  }

  const normalizedName = String(name ?? "").trim().toLowerCase();
  if (
    depth === 1 &&
    /^(main|run|start|entry|app|index|init|setup|bootstrap|execute)$/.test(normalizedName)
  ) {
    return "entrypoint";
  }

  if (/^[A-Z][A-Za-z0-9_]*$/.test(String(name ?? "")) && childCount > 0) {
    return "class";
  }

  if (childCount === 0) {
    return "helper";
  }

  return "function";
}

function normalizeNode(node, fallbackId = "") {
  const rawId = String(node?.id ?? node?.name ?? fallbackId).trim();
  const id = rawId || String(fallbackId || "node").trim();
  const name = String(node?.name ?? id).trim() || id;
  return {
    ...node,
    id,
    name,
    summary: String(node?.summary ?? ""),
    source: String(node?.source ?? node?.raw?.source ?? ""),
    kind: String(node?.kind ?? "function"),
    role: String(node?.role ?? ""),
  };
}

function buildFallbackDag(tree) {
  if (!tree || typeof tree !== "object") {
    return null;
  }

  const nodesById = new Map();
  const edgeSet = new Set();

  const visit = (node, depth = 0) => {
    if (!node || typeof node !== "object") {
      return;
    }

    const normalizedNode = normalizeNode(node);
    if (!normalizedNode.id) {
      return;
    }

    const existing = nodesById.get(normalizedNode.id);
    if (!existing) {
      nodesById.set(normalizedNode.id, {
        ...normalizedNode,
        depth,
      });
    } else if (depth < Number(existing.depth ?? depth)) {
      existing.depth = depth;
      nodesById.set(normalizedNode.id, existing);
    }

    const children = Array.isArray(node?.children) ? node.children : [];
    for (const child of children) {
      if (!child || typeof child !== "object") {
        continue;
      }
      const childId = String(child?.id ?? child?.name ?? "").trim();
      if (!childId) {
        continue;
      }
      edgeSet.add(edgeKey(normalizedNode.id, childId));
      visit(child, depth + 1);
    }
  };

  visit(tree, 0);

  const rootId = String(tree?.id ?? tree?.name ?? "").trim();
  const edges = [...edgeSet].map((key) => {
    const [source, target] = key.split("=>");
    return { source, target };
  });

  if (!rootId || nodesById.size === 0) {
    return null;
  }

  return {
    rootId,
    nodesById,
    edges,
  };
}

function normalizeDag(analysis) {
  const payload = analysis?.graph;
  if (payload && typeof payload === "object") {
    const nodesById = new Map();
    const rawNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
    for (const rawNode of rawNodes) {
      if (!rawNode || typeof rawNode !== "object") {
        continue;
      }
      const normalized = normalizeNode(rawNode);
      if (!normalized.id) {
        continue;
      }
      nodesById.set(normalized.id, normalized);
    }

    const edgeSet = new Set();
    const edges = [];
    const rawEdges = Array.isArray(payload.edges) ? payload.edges : [];
    for (const rawEdge of rawEdges) {
      if (!rawEdge || typeof rawEdge !== "object") {
        continue;
      }
      const source = String(rawEdge.source ?? "").trim();
      const target = String(rawEdge.target ?? "").trim();
      if (!source || !target) {
        continue;
      }
      if (!nodesById.has(source)) {
        nodesById.set(source, normalizeNode({ id: source, name: source }));
      }
      if (!nodesById.has(target)) {
        nodesById.set(target, normalizeNode({ id: target, name: target }));
      }
      const key = edgeKey(source, target);
      if (edgeSet.has(key)) {
        continue;
      }
      edgeSet.add(key);
      edges.push({ source, target });
    }

    let rootId = String(payload.root ?? analysis?.root ?? "").trim();
    if (!rootId || !nodesById.has(rootId)) {
      rootId = nodesById.keys().next().value ?? "";
    }
    if (!rootId) {
      return null;
    }
    if (!nodesById.has(rootId)) {
      nodesById.set(rootId, normalizeNode({ id: rootId, name: rootId }));
    }

    return {
      rootId,
      nodesById,
      edges,
    };
  }

  if (analysis?.tree && typeof analysis.tree === "object") {
    return buildFallbackDag(analysis.tree);
  }

  return null;
}

function computeDepths(rootId, outgoingByNode) {
  const depthByNode = new Map([[rootId, 0]]);
  const queue = [rootId];

  for (let index = 0; index < queue.length; index += 1) {
    const current = queue[index];
    const currentDepth = depthByNode.get(current) ?? 0;
    const children = outgoingByNode.get(current) ?? [];

    for (const child of children) {
      const nextDepth = currentDepth + 1;
      const knownDepth = depthByNode.get(child);
      if (knownDepth !== undefined && knownDepth <= nextDepth) {
        continue;
      }
      depthByNode.set(child, nextDepth);
      queue.push(child);
    }
  }

  return depthByNode;
}

function getVisibleSubgraph(rootId, outgoingByNode, expandedNodeIds, defaultDepth) {
  const visibleNodeIds = new Set([rootId]);
  const visibleEdges = new Set();
  const visibleEdgePairs = [];
  const depthByNode = new Map([[rootId, 0]]);
  const queue = [rootId];

  for (let index = 0; index < queue.length; index += 1) {
    const current = queue[index];
    const currentDepth = depthByNode.get(current) ?? 0;
    const canExpand = currentDepth < defaultDepth || expandedNodeIds.has(current);
    if (!canExpand) {
      continue;
    }

    const children = outgoingByNode.get(current) ?? [];
    for (const child of children) {
      const key = edgeKey(current, child);
      if (!visibleEdges.has(key)) {
        visibleEdges.add(key);
        visibleEdgePairs.push([current, child]);
      }

      visibleNodeIds.add(child);
      const nextDepth = currentDepth + 1;
      const knownDepth = depthByNode.get(child);
      if (knownDepth !== undefined && knownDepth <= nextDepth) {
        continue;
      }
      depthByNode.set(child, nextDepth);
      queue.push(child);
    }
  }

  return {
    visibleNodeIds,
    visibleEdgePairs,
    depthByNode,
  };
}

export function buildGraph(analysis, options = {}) {
  const dag = normalizeDag(analysis);
  if (!dag) {
    return { nodes: [], edges: [] };
  }

  const expandedNodeIds = options?.expandedNodeIds instanceof Set ? options.expandedNodeIds : new Set();
  const requestedDepth = Number(options?.defaultDepth);
  const defaultDepth = Number.isInteger(requestedDepth) && requestedDepth >= 0 ? requestedDepth : DEFAULT_DEPTH;

  const outgoingByNode = new Map();
  for (const nodeId of dag.nodesById.keys()) {
    outgoingByNode.set(nodeId, []);
  }
  for (const edge of dag.edges) {
    if (!outgoingByNode.has(edge.source)) {
      outgoingByNode.set(edge.source, []);
    }
    outgoingByNode.get(edge.source).push(edge.target);
  }
  for (const [nodeId, children] of outgoingByNode.entries()) {
    outgoingByNode.set(nodeId, [...new Set(children)].sort((left, right) => left.localeCompare(right)));
  }

  const globalDepth = computeDepths(dag.rootId, outgoingByNode);
  const visible = getVisibleSubgraph(dag.rootId, outgoingByNode, expandedNodeIds, defaultDepth);

  const levelBuckets = new Map();
  for (const nodeId of visible.visibleNodeIds) {
    const depth = visible.depthByNode.get(nodeId) ?? globalDepth.get(nodeId) ?? 0;
    if (!levelBuckets.has(depth)) {
      levelBuckets.set(depth, []);
    }
    levelBuckets.get(depth).push(nodeId);
  }

  const sortedDepths = [...levelBuckets.keys()].sort((left, right) => left - right);
  const rows = sortedDepths.map((depth) => {
    const nodeIds = levelBuckets.get(depth) ?? [];
    nodeIds.sort((left, right) => {
      const leftNode = dag.nodesById.get(left);
      const rightNode = dag.nodesById.get(right);
      const leftChildren = (outgoingByNode.get(left) ?? []).length;
      const rightChildren = (outgoingByNode.get(right) ?? []).length;
      const leftRole = inferRole(leftNode?.role, leftNode?.name ?? left, depth, leftChildren);
      const rightRole = inferRole(rightNode?.role, rightNode?.name ?? right, depth, rightChildren);
      const leftWeight = ROLE_WEIGHT[leftRole] ?? 99;
      const rightWeight = ROLE_WEIGHT[rightRole] ?? 99;
      if (leftWeight !== rightWeight) {
        return leftWeight - rightWeight;
      }
      return String(leftNode?.name ?? left).localeCompare(String(rightNode?.name ?? right));
    });

    const sizes = nodeIds.map((nodeId) => {
      const node = dag.nodesById.get(nodeId);
      const childCount = (outgoingByNode.get(nodeId) ?? []).length;
      const role = inferRole(node?.role, node?.name ?? nodeId, depth, childCount);
      return getNodeSize(role);
    });

    const rowWidth =
      sizes.reduce((total, size) => total + size.width, 0) + Math.max(0, sizes.length - 1) * HORIZONTAL_GAP;
    const rowHeight = sizes.reduce((maxHeight, size) => Math.max(maxHeight, size.height), 0);

    return {
      depth,
      nodeIds,
      rowWidth,
      rowHeight,
    };
  });

  const widestRowWidth = rows.reduce((maxWidth, row) => Math.max(maxWidth, row.rowWidth), 0);
  const nodePositions = new Map();
  const orderedVisibleNodeIds = [];
  let currentY = TOP_PADDING;

  for (const row of rows) {
    let currentX = LEFT_PADDING + (widestRowWidth - row.rowWidth) / 2;
    for (const nodeId of row.nodeIds) {
      const node = dag.nodesById.get(nodeId);
      const childCount = (outgoingByNode.get(nodeId) ?? []).length;
      const role = inferRole(node?.role, node?.name ?? nodeId, row.depth, childCount);
      const size = getNodeSize(role);
      nodePositions.set(nodeId, { x: currentX, y: currentY, role, width: size.width, height: size.height });
      orderedVisibleNodeIds.push(nodeId);
      currentX += size.width + HORIZONTAL_GAP;
    }
    currentY += row.rowHeight + LEVEL_GAP;
  }

  const visibleChildrenByNode = new Map();
  for (const [source] of visible.visibleEdgePairs) {
    visibleChildrenByNode.set(source, (visibleChildrenByNode.get(source) ?? 0) + 1);
  }

  const nodes = orderedVisibleNodeIds.map((nodeId, order) => {
    const node = dag.nodesById.get(nodeId);
    const positionInfo = nodePositions.get(nodeId);
    const depth = visible.depthByNode.get(nodeId) ?? globalDepth.get(nodeId) ?? 0;
    const childCount = (outgoingByNode.get(nodeId) ?? []).length;
    const role = positionInfo?.role ?? inferRole(node?.role, node?.name ?? nodeId, depth, childCount);
    const meta = ROLE_META[role] ?? ROLE_META.function;
    const projectCalls = normalizeList(node?.project_calls ?? node?.calls ?? outgoingByNode.get(nodeId) ?? []);
    const directCalls = normalizeList(node?.calls ?? outgoingByNode.get(nodeId) ?? []);
    const hiddenChildCount = Math.max(0, childCount - (visibleChildrenByNode.get(nodeId) ?? 0));

    return {
      id: nodeId,
      type: "analysisNode",
      position: {
        x: positionInfo?.x ?? LEFT_PADDING,
        y: positionInfo?.y ?? TOP_PADDING,
      },
      sourcePosition: "bottom",
      targetPosition: "top",
      data: {
        label: String(node?.name ?? nodeId),
        summary: String(node?.summary ?? ""),
        kind: String(node?.kind ?? "function"),
        calls: directCalls.length > 0 ? directCalls : projectCalls,
        projectCalls,
        stdlibCalls: normalizeList(node?.stdlib_calls),
        externalCalls: normalizeList(node?.external_calls),
        builtinCalls: normalizeList(node?.builtin_calls),
        decorators: normalizeList(node?.decorators),
        collapsedMembers: normalizeList(node?.collapsed_members),
        collapsedCount: Number(node?.collapsed_count ?? 0),
        collapseReason: String(node?.collapse_reason ?? ""),
        depth,
        childCount,
        hiddenChildCount,
        hasChildren: childCount > 0,
        expanded: expandedNodeIds.has(nodeId),
        canToggleExpand: childCount > 0,
        recursive: Boolean(node?.recursive),
        truncated: Boolean(node?.truncated),
        role,
        roleLabel: meta.label,
        roleAccent: meta.accent,
        roleGlyph: meta.glyph,
        order,
        raw: {
          ...node,
          source: String(node?.source ?? ""),
        },
      },
      style: {
        width: positionInfo?.width ?? (ROLE_META.function?.width ?? 240),
        height: positionInfo?.height ?? (ROLE_META.function?.height ?? 116),
      },
    };
  });

  const edges = visible.visibleEdgePairs
    .filter(([source, target]) => visible.visibleNodeIds.has(source) && visible.visibleNodeIds.has(target))
    .map(([source, target], index) => ({
      id: `e-${slugify(source)}-${slugify(target)}-${index}`,
      source,
      target,
      type: "bezier",
    }));

  return { nodes, edges };
}
