const CHILD_GAP = 72;
const ROW_GAP = 84;
const LEVEL_GAP = 124;
const TOP_PADDING = 96;
const LEFT_PADDING = 96;

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

function normalizeList(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))];
}

function collectChildNames(children) {
  return children.map((child) => String(child?.name ?? "node")).filter(Boolean);
}

function inferRole(node, depth, childCount) {
  if (String(node?.kind ?? "") === "cluster" || Number(node?.collapsed_count ?? 0) > 0) {
    return "cluster";
  }

  if (depth === 0) {
    return "root";
  }

  const name = String(node?.name ?? "");
  const normalized = name.toLowerCase();

  if (
    depth === 1 &&
    /^(main|run|start|entry|app|index|init|setup|bootstrap|execute)$/.test(normalized)
  ) {
    return "entrypoint";
  }

  if (/^[A-Z][A-Za-z0-9_]*$/.test(name) && childCount > 0) {
    return "class";
  }

  if (childCount === 0) {
    return "helper";
  }

  return "function";
}

function getNodeSize(role) {
  const meta = ROLE_META[role] ?? ROLE_META.function;
  return {
    width: meta.width,
    height: meta.height,
  };
}

function getCallList(node, childNodes) {
  if (String(node?.kind ?? "") === "cluster") {
    const collapsedMembers = normalizeList(node?.collapsed_members);
    if (collapsedMembers.length > 0) {
      return collapsedMembers;
    }
  }

  const projectCalls = normalizeList(node?.project_calls);
  if (projectCalls.length > 0) {
    return projectCalls;
  }

  const directCalls = normalizeList(node?.calls);
  if (directCalls.length > 0) {
    return directCalls;
  }

  return collectChildNames(childNodes);
}

function shiftNodes(nodes, dx, dy) {
  return nodes.map((node) => ({
    ...node,
    position: {
      x: node.position.x + dx,
      y: node.position.y + dy,
    },
  }));
}

function getChildRows(childLayouts) {
  if (childLayouts.length < 4) {
    return [childLayouts];
  }

  const rows = [[], []];
  const rowWidths = [0, 0];

  [...childLayouts]
    .sort((a, b) => b.width - a.width)
    .forEach((layout) => {
      const rowIndex = rowWidths[0] <= rowWidths[1] ? 0 : 1;
      rows[rowIndex].push(layout);
      rowWidths[rowIndex] += layout.width + CHILD_GAP;
    });

  return rows.map((row) => row.sort((a, b) => a.order - b.order));
}

function createNodeRecord(node, id, depth, childCount, rawChildren, role, order) {
  const meta = ROLE_META[role] ?? ROLE_META.function;
  const size = getNodeSize(role);

  return {
    id,
    type: "analysisNode",
    position: {
      x: 0,
      y: 0,
    },
    sourcePosition: "bottom",
    targetPosition: "top",
    data: {
      label: String(node?.name ?? "Untitled"),
      summary: String(node?.summary ?? ""),
      kind: String(node?.kind ?? ""),
      calls: getCallList(node, rawChildren),
      projectCalls: normalizeList(node?.project_calls),
      stdlibCalls: normalizeList(node?.stdlib_calls),
      externalCalls: normalizeList(node?.external_calls),
      builtinCalls: normalizeList(node?.builtin_calls),
      decorators: normalizeList(node?.decorators),
      collapsedMembers: normalizeList(node?.collapsed_members),
      collapsedCount: Number(node?.collapsed_count ?? 0),
      collapseReason: String(node?.collapse_reason ?? ""),
      depth,
      childCount,
      hasChildren: childCount > 0,
      recursive: Boolean(node?.recursive),
      truncated: Boolean(node?.truncated),
      role,
      roleLabel: meta.label,
      roleAccent: meta.accent,
      roleGlyph: meta.glyph,
      order,
      raw: node,
    },
    style: {
      width: size.width,
      height: size.height,
    },
  };
}

function layoutNode(node, depth = 0, parentId = "", siblingIndex = 0) {
  const children = Array.isArray(node?.children)
    ? node.children.filter((child) => child && typeof child === "object")
    : [];

  const safeName = slugify(node?.name);
  const id = parentId ? `${parentId}/${safeName}-${siblingIndex}` : `root/${safeName}`;
  const role = inferRole(node, depth, children.length);
  const nodeSize = getNodeSize(role);
  const childLayouts = children.map((child, index) => layoutNode(child, depth + 1, id, index));
  const nodeRecord = createNodeRecord(node, id, depth, childLayouts.length, children, role, siblingIndex);

  if (childLayouts.length === 0) {
    return {
      id,
      width: nodeSize.width,
      height: nodeSize.height,
      nodes: [
        {
          ...nodeRecord,
          position: {
            x: 0,
            y: 0,
          },
        },
      ],
      edges: [],
    };
  }

  const rows = getChildRows(childLayouts);
  const rowMetrics = rows.map((row) => {
    const width =
      row.reduce((total, layout) => total + layout.width, 0) + Math.max(0, row.length - 1) * CHILD_GAP;
    const height = row.reduce((maxHeight, layout) => Math.max(maxHeight, layout.height), 0);

    return { width, height };
  });

  const width = Math.max(nodeSize.width, ...rowMetrics.map((metric) => metric.width));
  const nodes = [
    {
      ...nodeRecord,
      position: {
        x: (width - nodeSize.width) / 2,
        y: 0,
      },
    },
  ];
  const edges = [];

  let currentY = nodeSize.height + LEVEL_GAP;

  rows.forEach((row, rowIndex) => {
    const rowWidth = rowMetrics[rowIndex].width;
    let currentX = (width - rowWidth) / 2;

    row.forEach((childLayout) => {
      nodes.push(...shiftNodes(childLayout.nodes, currentX, currentY));
      edges.push(...childLayout.edges);
      edges.push({
        id: `e-${id}-${childLayout.id}`,
        source: id,
        target: childLayout.id,
        type: "bezier",
      });
      currentX += childLayout.width + CHILD_GAP;
    });

    currentY += rowMetrics[rowIndex].height + ROW_GAP;
  });

  return {
    id,
    width,
    height: currentY - ROW_GAP,
    nodes,
    edges,
  };
}

export function buildGraph(tree) {
  if (!tree || typeof tree !== "object") {
    return { nodes: [], edges: [] };
  }

  const layout = layoutNode(tree);
  const nodes = layout.nodes.map((node) => ({ ...node }));
  const edges = layout.edges.map((edge) => ({ ...edge }));

  if (nodes.length === 0) {
    return { nodes, edges };
  }

  const minX = Math.min(...nodes.map((node) => node.position.x));
  const minY = Math.min(...nodes.map((node) => node.position.y));
  const shiftX = LEFT_PADDING - minX;
  const shiftY = TOP_PADDING - minY;

  for (const node of nodes) {
    node.position = {
      x: node.position.x + shiftX,
      y: node.position.y + shiftY,
    };
  }

  return { nodes, edges };
}
