const ROLE_COLORS = {
  root: {
    fill: "#2b240b",
    stroke: "#facc15",
  },
  class: {
    fill: "#241036",
    stroke: "#a855f7",
  },
  entrypoint: {
    fill: "#351a10",
    stroke: "#fb923c",
  },
  helper: {
    fill: "#13271a",
    stroke: "#22c55e",
  },
  function: {
    fill: "#10223f",
    stroke: "#60a5fa",
  },
};

function escapeXml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function sanitizeFilename(value) {
  return String(value ?? "graph")
    .trim()
    .toLowerCase()
    .replace(/['"]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "graph";
}

function wrapText(text, limit) {
  const words = String(text ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return [];
  }

  const lines = [];
  let current = "";

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= limit || current.length === 0) {
      current = next;
      continue;
    }

    lines.push(current);
    current = word;
  }

  if (current) {
    lines.push(current);
  }

  return lines;
}

function getNodeBox(node) {
  const width = Number(node?.style?.width ?? 240);
  const height = Number(node?.style?.height ?? 116);
  const x = Number(node?.position?.x ?? 0);
  const y = Number(node?.position?.y ?? 0);

  return {
    x,
    y,
    width,
    height,
    role: String(node?.data?.role ?? "function"),
    label: String(node?.data?.label ?? "Untitled"),
    summary: String(node?.data?.summary ?? ""),
  };
}

function getBounds(nodes) {
  if (nodes.length === 0) {
    return { width: 1200, height: 800, minX: 0, minY: 0 };
  }

  const boxes = nodes.map(getNodeBox);
  const minX = Math.min(...boxes.map((box) => box.x));
  const minY = Math.min(...boxes.map((box) => box.y));
  const maxX = Math.max(...boxes.map((box) => box.x + box.width));
  const maxY = Math.max(...boxes.map((box) => box.y + box.height));
  const margin = 72;

  return {
    minX,
    minY,
    width: maxX - minX + margin * 2,
    height: maxY - minY + margin * 2,
    margin,
  };
}

function getNodePosition(box, bounds) {
  return {
    x: box.x - bounds.minX + bounds.margin,
    y: box.y - bounds.minY + bounds.margin,
  };
}

function getEdgePath(sourceBox, targetBox, bounds) {
  const source = getNodePosition(sourceBox, bounds);
  const target = getNodePosition(targetBox, bounds);
  const startX = source.x + sourceBox.width / 2;
  const startY = source.y + sourceBox.height;
  const endX = target.x + targetBox.width / 2;
  const endY = target.y;
  const distance = Math.max(84, Math.abs(endY - startY) * 0.45);
  const controlY1 = startY + distance;
  const controlY2 = endY - distance;

  return `M ${startX} ${startY} C ${startX} ${controlY1}, ${endX} ${controlY2}, ${endX} ${endY}`;
}

function renderTextLines(lines, x, y, lineHeight, fill, size, weight = 400) {
  return lines
    .map(
      (line, index) =>
        `<text x="${x}" y="${y + index * lineHeight}" fill="${fill}" font-size="${size}" font-weight="${weight}" text-anchor="middle">${escapeXml(line)}</text>`,
    )
    .join("");
}

function createSvg(graph, selectedNodeId, title) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];
  const bounds = getBounds(nodes);
  const nodeMap = new Map(nodes.map((node) => [node.id, getNodeBox(node)]));

  const edgeMarkup = edges
    .filter((edge) => nodeMap.has(edge.source) && nodeMap.has(edge.target))
    .map((edge) => {
      const path = getEdgePath(nodeMap.get(edge.source), nodeMap.get(edge.target), bounds);
      return `<path d="${path}" fill="none" stroke="rgba(148, 163, 184, 0.2)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />`;
    })
    .join("");

  const nodeMarkup = nodes
    .map((node) => {
      const box = getNodeBox(node);
      const position = getNodePosition(box, bounds);
      const roleMeta = ROLE_COLORS[box.role] ?? ROLE_COLORS.function;
      const selected = selectedNodeId === node.id;
      const titleLines = wrapText(box.label, 24).slice(0, 2);
      const innerX = position.x + box.width / 2;
      const innerY = position.y + box.height / 2 - ((titleLines.length - 1) * 18) / 2 + 6;

      return `
        <g>
          <rect x="${position.x}" y="${position.y}" width="${box.width}" height="${box.height}" rx="18" ry="18" fill="${roleMeta.fill}" stroke="${selected ? "rgba(255,255,255,0.9)" : roleMeta.stroke}" stroke-width="${selected ? 2.2 : 1.6}" />
          <rect x="${position.x + 12}" y="${position.y + 12}" width="${box.width - 24}" height="${box.height - 24}" rx="14" ry="14" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.03)" stroke-width="1" />
          ${renderTextLines(titleLines, innerX, innerY, 18, "#f8fbff", 16, 700)}
        </g>
      `;
    })
    .join("");

  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="${bounds.width}" height="${bounds.height}" viewBox="0 0 ${bounds.width} ${bounds.height}">
      <defs>
        <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#09090d" />
          <stop offset="100%" stop-color="#060709" />
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#bg)" />
      <g>
        ${edgeMarkup}
        ${nodeMarkup}
      </g>
    </svg>
  `;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadGraphSvg(graph, selectedNodeId, title) {
  const svg = createSvg(graph, selectedNodeId, title);
  const filename = `${sanitizeFilename(title)}.svg`;
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  downloadBlob(blob, filename);
}

export async function downloadGraphPng(graph, selectedNodeId, title) {
  const svg = createSvg(graph, selectedNodeId, title);
  const bounds = getBounds(Array.isArray(graph?.nodes) ? graph.nodes : []);
  const svgBlob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const svgUrl = URL.createObjectURL(svgBlob);

  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = reject;
      image.src = svgUrl;
    });

    const scale = 1;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bounds.width * scale);
    canvas.height = Math.round(bounds.height * scale);

    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Canvas is not available.");
    }

    context.scale(scale, scale);
    context.drawImage(image, 0, 0, bounds.width, bounds.height);

    const pngBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!pngBlob) {
      throw new Error("Could not create PNG export.");
    }

    downloadBlob(pngBlob, `${sanitizeFilename(title)}.png`);
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}
