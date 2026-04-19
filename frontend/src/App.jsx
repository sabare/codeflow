import { useEffect, useMemo, useRef, useState } from "react";
import { ControlDrawer } from "./components/ControlDrawer.jsx";
import { GraphCanvas } from "./components/GraphCanvas.jsx";
import { SearchPalette } from "./components/SearchPalette.jsx";
import { buildGraph } from "./lib/buildGraph.js";
import { downloadGraphPng, downloadGraphSvg } from "./lib/exportGraph.js";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const DEFAULT_VISIBLE_GRAPH_DEPTH = 1;

export default function App() {
  const [folderPath, setFolderPath] = useState("");
  const [currentDirectory, setCurrentDirectory] = useState(null);
  const [directoryEntries, setDirectoryEntries] = useState({
    directories: [],
    files: [],
    parent: null,
  });
  const [selectedFile, setSelectedFile] = useState(null);
  const [functions, setFunctions] = useState([]);
  const [selectedFunction, setSelectedFunction] = useState("");
  const [flowMaxDepth, setFlowMaxDepth] = useState("");
  const [includeStdlib, setIncludeStdlib] = useState(true);
  const [includeExternal, setIncludeExternal] = useState(true);
  const [includeBuiltin, setIncludeBuiltin] = useState(true);
  const [analysis, setAnalysis] = useState(null);
  const [analysisRequest, setAnalysisRequest] = useState(null);
  const [expandedNodeIds, setExpandedNodeIds] = useState(() => new Set());
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState("browse");
  const [loadingDirectory, setLoadingDirectory] = useState(false);
  const [loadingFunctions, setLoadingFunctions] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef(null);

  const graph = useMemo(() => {
    if (!analysis || typeof analysis !== "object") {
      return { nodes: [], edges: [] };
    }

    return buildGraph(analysis, {
      expandedNodeIds,
      defaultDepth: DEFAULT_VISIBLE_GRAPH_DEPTH,
    });
  }, [analysis, expandedNodeIds]);

  const selectedNode = useMemo(
    () => graph.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [graph.nodes, selectedNodeId],
  );
  const graphTitle = String(analysis?.tree?.name ?? selectedFunction ?? currentDirectory ?? "graph");
  const hasGraph = graph.nodes.length > 0;

  function buildAnalyzeParams(request) {
    const params = new URLSearchParams({
      path: request.path,
      function: request.functionName,
      include_stdlib: String(request.includeStdlib),
      include_external: String(request.includeExternal),
      include_builtin: String(request.includeBuiltin),
    });

    if (request.maxDepth !== null) {
      params.set("max_depth", String(request.maxDepth));
    }

    return params;
  }

  const searchResults = useMemo(() => {
    const query = paletteQuery.trim().toLowerCase();
    if (!query) {
      return [];
    }

    const tokens = query.split(/\s+/).filter(Boolean);
    const results = [];
    const seen = new Set();

    const addResult = (result, haystack) => {
      const text = String(haystack ?? "").toLowerCase();
      if (!tokens.every((token) => text.includes(token))) {
        return;
      }
      if (seen.has(result.id)) {
        return;
      }

      let score = 3;
      if (text === query) {
        score = 0;
      } else if (text.startsWith(query)) {
        score = 1;
      } else if (text.includes(query)) {
        score = 2;
      }

      seen.add(result.id);
      results.push({ ...result, score });
    };

    for (const node of graph.nodes) {
      const label = String(node.data?.label ?? "");
      const name = String(node.data?.raw?.name ?? label);
      const summary = String(node.data?.summary ?? "");
      const role = String(node.data?.roleLabel ?? node.data?.role ?? "symbol");
      const haystack = [label, name, summary, role].filter(Boolean).join(" ");

      addResult(
        {
          id: `symbol:${node.id}`,
          type: "symbol",
          title: name || label || "Untitled",
          subtitle: summary || role,
          nodeId: node.id,
        },
        haystack,
      );

      if (summary) {
        addResult(
          {
            id: `phrase:${node.id}`,
            type: "phrase",
            title: summary.slice(0, 72),
            subtitle: name || label || "Node summary",
            nodeId: node.id,
          },
          summary,
        );
      }
    }

    for (const file of directoryEntries.files) {
      const haystack = [file.name, file.path].filter(Boolean).join(" ");
      addResult(
        {
          id: `file:${file.path}`,
          type: "file",
          title: file.name,
          subtitle: file.path,
          file,
        },
        haystack,
      );
    }

    for (const name of functions) {
      const haystack = [name, selectedFile?.name ?? ""].filter(Boolean).join(" ");
      addResult(
        {
          id: `function:${name}`,
          type: "function",
          title: name,
          subtitle: selectedFile?.name || "Current file",
          functionName: name,
        },
        haystack,
      );
    }

    return results
      .sort((left, right) => left.score - right.score || left.type.localeCompare(right.type) || left.title.localeCompare(right.title))
      .slice(0, 12);
  }, [directoryEntries.files, functions, graph.nodes, paletteQuery, selectedFile]);

  useEffect(() => {
    if (graph.nodes.length === 0) {
      setSelectedNodeId("");
      return;
    }

    setSelectedNodeId((current) => {
      if (current && graph.nodes.some((node) => node.id === current)) {
        return current;
      }

      const rootNode = graph.nodes.find((node) => node.data?.depth === 0) ?? graph.nodes[0];
      return rootNode?.id ?? "";
    });
  }, [graph.nodes]);

  useEffect(() => {
    if (!analysisRequest || analysis?.flow_explanation_status !== "pending") {
      return undefined;
    }

    let cancelled = false;

    const pollExplanation = async () => {
      try {
        const fingerprint = String(analysis?.flow_fingerprint ?? "").trim();
        if (!fingerprint) {
          return;
        }

        const response = await fetch(`${API_URL}/flow-explanation?flow_fingerprint=${encodeURIComponent(fingerprint)}`);

        if (!response.ok) {
          return;
        }

        const data = await response.json();
        if (cancelled) {
          return;
        }

        if (data?.flow_explanation_status && data.flow_explanation_status !== "pending") {
          setAnalysis((current) => (current ? { ...current, ...data } : current));
        }
      } catch {
        // Keep the deterministic graph visible; a later poll can retry.
      }
    };

    const interval = window.setInterval(pollExplanation, 1800);
    pollExplanation();

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [analysis?.flow_explanation_status, analysis?.flow_fingerprint, analysisRequest]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
      }

      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "m") {
        event.preventDefault();
        setExportMenuOpen((current) => !current);
      }

      if (event.key === "Escape") {
        setPaletteOpen(false);
        setExportMenuOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!exportMenuOpen) {
      return undefined;
    }

    const onPointerDown = (event) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(event.target)) {
        setExportMenuOpen(false);
      }
    };

    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [exportMenuOpen]);

  async function loadDirectory(path) {
    const trimmedPath = String(path ?? "").trim();
    if (!trimmedPath) {
      setError("Enter a project path first.");
      return;
    }

    setLoadingDirectory(true);
    setError("");
    setAnalysis(null);
    setAnalysisRequest(null);
    setExpandedNodeIds(new Set());

    try {
      const response = await fetch(`${API_URL}/browse?path=${encodeURIComponent(trimmedPath)}`);

      if (!response.ok) {
        let message = `Request failed with status ${response.status}`;
        try {
          const payload = await response.json();
          message = payload.detail || payload.error || message;
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      const data = await response.json();
      setCurrentDirectory(data.path);
      setDirectoryEntries({
        directories: Array.isArray(data.directories) ? data.directories : [],
        files: Array.isArray(data.files) ? data.files : [],
        parent: data.parent ?? null,
      });
      setSelectedFile(null);
      setFunctions([]);
      setSelectedFunction("");
      setDrawerTab("browse");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoadingDirectory(false);
    }
  }

  async function handleLoadFolder(event) {
    event.preventDefault();
    await loadDirectory(folderPath.trim());
  }

  async function handleOpenDirectory(path) {
    await loadDirectory(path);
  }

  async function handleSelectFile(file) {
    setSelectedFile(file);
    setSelectedFunction("");
    setFunctions([]);
    setLoadingFunctions(true);
    setError("");
    setAnalysis(null);
    setAnalysisRequest(null);
    setExpandedNodeIds(new Set());
    setDrawerTab("functions");
    setDrawerOpen(true);

    try {
      const response = await fetch(`${API_URL}/functions?path=${encodeURIComponent(file.path)}`);

      if (!response.ok) {
        let message = `Request failed with status ${response.status}`;
        try {
          const payload = await response.json();
          message = payload.detail || payload.error || message;
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      const data = await response.json();
      const nextFunctions = Array.isArray(data.functions) ? data.functions : [];
      setFunctions(nextFunctions);
      setSelectedFunction(nextFunctions[0] || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoadingFunctions(false);
    }
  }

  async function handleAnalyzeFunction(event) {
    event.preventDefault();

    if (!folderPath.trim()) {
      setError("Load a folder first.");
      setDrawerTab("browse");
      return;
    }
    if (!selectedFile) {
      setError("Choose a file first.");
      setDrawerTab("functions");
      return;
    }
    if (!selectedFunction) {
      setError("Choose a function name first.");
      setDrawerTab("functions");
      return;
    }

    const trimmedDepth = flowMaxDepth.trim();
    let parsedDepth = null;
    if (trimmedDepth) {
      parsedDepth = Number(trimmedDepth);
      if (!Number.isInteger(parsedDepth) || parsedDepth < 0) {
        setError("Max depth must be a non-negative integer or left blank.");
        setDrawerTab("functions");
        return;
      }
    }

    setLoadingAnalysis(true);
    setError("");
    setAnalysis(null);
    setAnalysisRequest(null);
    setExpandedNodeIds(new Set());

    try {
      const request = {
        path: folderPath.trim(),
        functionName: selectedFunction,
        maxDepth: parsedDepth,
        includeStdlib,
        includeExternal,
        includeBuiltin,
      };
      const params = buildAnalyzeParams(request);

      const response = await fetch(`${API_URL}/analyze?${params.toString()}`);

      if (!response.ok) {
        let message = `Request failed with status ${response.status}`;
        try {
          const payload = await response.json();
          message = payload.detail || payload.error || message;
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      const data = await response.json();
      if (!data || typeof data.tree !== "object" || data.tree === null) {
        throw new Error("The API did not return a tree.");
      }

      setAnalysis(data);
      setAnalysisRequest(request);
      setDrawerTab("flow");
      setDrawerOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoadingAnalysis(false);
    }
  }

  function handleSelectNode(nodeId) {
    setSelectedNodeId(nodeId);
    setDrawerTab("node");
    if (!drawerOpen) {
      setDrawerOpen(true);
    }
  }

  function handleToggleNodeExpansion(nodeId) {
    setExpandedNodeIds((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }

  function handleExportSvg() {
    downloadGraphSvg(graph, selectedNodeId, graphTitle);
  }

  async function handleExportPng() {
    await downloadGraphPng(graph, selectedNodeId, graphTitle);
  }

  async function handlePickSearchResult(result) {
    setPaletteOpen(false);
    setPaletteQuery("");

    if (result?.type === "file" && result.file) {
      await handleSelectFile(result.file);
      return;
    }

    if (result?.type === "function" && result.functionName) {
      setSelectedFunction(result.functionName);
      setDrawerTab("functions");
      setDrawerOpen(true);
      return;
    }

    if ((result?.type === "symbol" || result?.type === "phrase") && result.nodeId) {
      handleSelectNode(result.nodeId);
    }
  }

  return (
    <main className="app-shell">
      <div className="app-backdrop" aria-hidden="true" />

      <div className="app-toolbar app-toolbar-right" aria-label="Workspace actions">
        <button
          className="top-icon-button"
          type="button"
          onClick={() => setPaletteOpen(true)}
          aria-label="Open search palette"
          title="Search (Cmd/Ctrl+K)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="M16 16l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
        <div ref={exportMenuRef} className="export-menu-anchor">
          <button
            className="top-icon-button"
            type="button"
            onClick={() => setExportMenuOpen((current) => !current)}
            disabled={!hasGraph}
            aria-label="Export graph"
            aria-expanded={exportMenuOpen}
            aria-haspopup="menu"
            title="Export (Cmd/Ctrl+M)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M7.25 4.75h6.75L18 8.75v10.5H7.25z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path d="M12 6.5v8.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              <path d="M9.25 11.75L12 14.5l2.75-2.75" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {exportMenuOpen ? (
            <div className="export-menu" role="menu" aria-label="Export options">
              <button
                className="export-menu-item"
                type="button"
                role="menuitem"
                onClick={() => {
                  setExportMenuOpen(false);
                  handleExportSvg();
                }}
              >
                <span>SVG</span>
                <small>Vector export</small>
              </button>
              <button
                className="export-menu-item"
                type="button"
                role="menuitem"
                onClick={() => {
                  setExportMenuOpen(false);
                  handleExportPng();
                }}
              >
                <span>PNG</span>
                <small>Image export</small>
              </button>
              <div className="export-menu-divider" aria-hidden="true" />
              <button className="export-menu-item export-menu-item-muted" type="button" disabled>
                <span>Share later</span>
                <small>Copy link, WhatsApp, more</small>
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <GraphCanvas
        nodes={graph.nodes}
        edges={graph.edges}
        selectedNodeId={selectedNodeId}
        onNodeSelect={handleSelectNode}
        onNodeToggleExpand={handleToggleNodeExpansion}
        isLoading={loadingAnalysis}
      />

      <ControlDrawer
        open={drawerOpen}
        activeTab={drawerTab}
        onTabChange={setDrawerTab}
        onOpenChange={setDrawerOpen}
        folderPath={folderPath}
        setFolderPath={setFolderPath}
        currentDirectory={currentDirectory}
        directoryEntries={directoryEntries}
        selectedFile={selectedFile}
        functions={functions}
        selectedFunction={selectedFunction}
        setSelectedFunction={setSelectedFunction}
        analysis={analysis}
        selectedNode={selectedNode}
        loadingDirectory={loadingDirectory}
        loadingFunctions={loadingFunctions}
        loadingAnalysis={loadingAnalysis}
        error={error}
        flowMaxDepth={flowMaxDepth}
        setFlowMaxDepth={setFlowMaxDepth}
        includeStdlib={includeStdlib}
        setIncludeStdlib={setIncludeStdlib}
        includeExternal={includeExternal}
        setIncludeExternal={setIncludeExternal}
        includeBuiltin={includeBuiltin}
        setIncludeBuiltin={setIncludeBuiltin}
        onLoadFolder={handleLoadFolder}
        onOpenDirectory={handleOpenDirectory}
        onSelectFile={handleSelectFile}
        onAnalyzeFunction={handleAnalyzeFunction}
      />

      <SearchPalette
        open={paletteOpen}
        query={paletteQuery}
        results={searchResults}
        onQueryChange={setPaletteQuery}
        onClose={() => setPaletteOpen(false)}
        onPick={handlePickSearchResult}
      />
    </main>
  );
}
