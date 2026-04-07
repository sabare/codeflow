import { useEffect, useMemo, useState } from "react";
import { ControlDrawer } from "./components/ControlDrawer.jsx";
import { GraphCanvas } from "./components/GraphCanvas.jsx";
import { buildGraph } from "./lib/buildGraph.js";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
  const [analysis, setAnalysis] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState("browse");
  const [loadingDirectory, setLoadingDirectory] = useState(false);
  const [loadingFunctions, setLoadingFunctions] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState("");

  const graph = useMemo(() => {
    if (!analysis || typeof analysis.tree !== "object" || analysis.tree === null) {
      return { nodes: [], edges: [] };
    }

    return buildGraph(analysis.tree);
  }, [analysis]);

  const selectedNode = useMemo(
    () => graph.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [graph.nodes, selectedNodeId],
  );

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

  async function loadDirectory(path) {
    const trimmedPath = String(path ?? "").trim();
    if (!trimmedPath) {
      setError("Enter a project path first.");
      return;
    }

    setLoadingDirectory(true);
    setError("");
    setAnalysis(null);

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
    setDrawerTab("functions");

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

    setLoadingAnalysis(true);
    setError("");
    setAnalysis(null);

    try {
      const response = await fetch(
        `${API_URL}/analyze?path=${encodeURIComponent(folderPath.trim())}&function=${encodeURIComponent(selectedFunction)}`,
      );

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
      setDrawerTab("node");
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

  return (
    <main className="app-shell">
      <div className="app-backdrop" aria-hidden="true" />

      <GraphCanvas
        nodes={graph.nodes}
        edges={graph.edges}
        selectedNodeId={selectedNodeId}
        onNodeSelect={handleSelectNode}
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
        onLoadFolder={handleLoadFolder}
        onOpenDirectory={handleOpenDirectory}
        onSelectFile={handleSelectFile}
        onAnalyzeFunction={handleAnalyzeFunction}
      />
    </main>
  );
}
