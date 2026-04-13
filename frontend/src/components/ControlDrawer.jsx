function normalizeList(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))];
}

function Section({ title, items, emptyLabel }) {
  return (
    <section className="drawer-section">
      <div className="drawer-section-head">
        <h3>{title}</h3>
        <span>{items.length}</span>
      </div>

      {items.length > 0 ? (
        <div className="tag-list">
          {items.map((item) => (
            <span key={item} className="tag-pill">
              {item}
            </span>
          ))}
        </div>
      ) : (
        <p className="drawer-empty-line">{emptyLabel}</p>
      )}
    </section>
  );
}

export function ControlDrawer({
  open,
  activeTab,
  onTabChange,
  onOpenChange,
  folderPath,
  setFolderPath,
  currentDirectory,
  directoryEntries,
  selectedFile,
  functions,
  selectedFunction,
  setSelectedFunction,
  analysis,
  selectedNode,
  loadingDirectory,
  loadingFunctions,
  loadingAnalysis,
  error,
  flowMaxDepth,
  setFlowMaxDepth,
  includeStdlib,
  setIncludeStdlib,
  includeExternal,
  setIncludeExternal,
  includeBuiltin,
  setIncludeBuiltin,
  onLoadFolder,
  onOpenDirectory,
  onSelectFile,
  onAnalyzeFunction,
}) {
  const node = selectedNode?.data ?? null;
  const sourceSnippet = String(node?.raw?.source ?? "").trim();
  const projectCalls = normalizeList(node?.projectCalls);
  const directCalls = normalizeList(node?.calls);
  const stdlibCalls = normalizeList(node?.stdlibCalls);
  const externalCalls = normalizeList(node?.externalCalls);
  const builtinCalls = normalizeList(node?.builtinCalls);
  const decorators = normalizeList(node?.decorators);
  const callPills = projectCalls.length > 0 ? projectCalls : directCalls;
  const hasAnalysis = Boolean(analysis?.tree);

  return (
    <>
      {!open ? (
        <button className="drawer-toggle" type="button" onClick={() => onOpenChange(true)} aria-label="Open controls">
          <span aria-hidden="true">☰</span>
        </button>
      ) : null}

      <aside className={`control-drawer ${open ? "control-drawer-open" : "control-drawer-closed"}`}>
        <div className="drawer-surface">
          <div className="drawer-head">
            <div>
              <p className="drawer-kicker">Code Analysis Visualizer</p>
              <h2>{activeTab === "node" ? "Node Inspector" : "Project Controls"}</h2>
            </div>
            <button
              className="icon-button"
              type="button"
              onClick={() => onOpenChange(false)}
              aria-label="Close controls"
            >
              ×
            </button>
          </div>

          <div className="drawer-tabs" role="tablist" aria-label="Workspace tabs">
            <button
              type="button"
              className={`drawer-tab ${activeTab === "browse" ? "drawer-tab-active" : ""}`}
              onClick={() => onTabChange("browse")}
              role="tab"
              aria-selected={activeTab === "browse"}
            >
              Browse
            </button>
            <button
              type="button"
              className={`drawer-tab ${activeTab === "functions" ? "drawer-tab-active" : ""}`}
              onClick={() => onTabChange("functions")}
              role="tab"
              aria-selected={activeTab === "functions"}
            >
              Functions
            </button>
            <button
              type="button"
              className={`drawer-tab ${activeTab === "node" ? "drawer-tab-active" : ""}`}
              onClick={() => onTabChange("node")}
              role="tab"
              aria-selected={activeTab === "node"}
            >
              Node
            </button>
          </div>

          <div className="drawer-body">
            {activeTab === "browse" ? (
              <div className="drawer-panel" role="tabpanel">
                <form className="drawer-form" onSubmit={onLoadFolder}>
                  <label className="field-label" htmlFor="project-path">
                    Project path
                  </label>
                  <div className="path-row path-row-drawer">
                    <input
                      id="project-path"
                      className="path-input"
                      type="text"
                      value={folderPath}
                      onChange={(event) => setFolderPath(event.target.value)}
                      placeholder="/Users/you/projects/my-app"
                      spellCheck={false}
                      autoComplete="off"
                    />
                    <button className="primary-button compact" type="submit" disabled={loadingDirectory}>
                      {loadingDirectory ? "Loading..." : "Load"}
                    </button>
                  </div>
                </form>

                <div className="drawer-meta">
                  <div className="drawer-meta-chip">
                    <span>Current</span>
                    <strong>{currentDirectory || "No folder loaded"}</strong>
                  </div>
                  {directoryEntries.parent ? (
                    <button
                      className="drawer-link"
                      type="button"
                      onClick={() => onOpenDirectory(directoryEntries.parent)}
                    >
                      Go to parent
                    </button>
                  ) : null}
                </div>

                <section className="drawer-section">
                  <div className="drawer-section-head">
                    <h3>Subdirectories</h3>
                    <span>{directoryEntries.directories.length}</span>
                  </div>
                  <div className="drawer-list">
                    {directoryEntries.directories.length > 0 ? (
                      directoryEntries.directories.map((entry) => (
                        <button
                          type="button"
                          key={entry.path}
                          className="drawer-item"
                          onClick={() => onOpenDirectory(entry.path)}
                        >
                          {entry.name}
                        </button>
                      ))
                    ) : (
                      <p className="drawer-empty-line">No subdirectories found.</p>
                    )}
                  </div>
                </section>

                <section className="drawer-section">
                  <div className="drawer-section-head">
                    <h3>Files</h3>
                    <span>{directoryEntries.files.length}</span>
                  </div>
                  <div className="drawer-list">
                    {directoryEntries.files.length > 0 ? (
                      directoryEntries.files.map((file) => (
                        <button
                          type="button"
                          key={file.path}
                          className={`drawer-item ${selectedFile?.path === file.path ? "drawer-item-active" : ""}`}
                          onClick={() => onSelectFile(file)}
                        >
                          {file.name}
                        </button>
                      ))
                    ) : (
                      <p className="drawer-empty-line">No Python files found.</p>
                    )}
                  </div>
                </section>
              </div>
            ) : null}

            {activeTab === "functions" ? (
              <div className="drawer-panel" role="tabpanel">
                <div className="drawer-meta">
                  <div className="drawer-meta-chip">
                    <span>Selected file</span>
                    <strong>{selectedFile?.name || "Choose a file in Browse"}</strong>
                  </div>
                  <div className="drawer-meta-chip">
                    <span>Functions</span>
                    <strong>{functions.length}</strong>
                  </div>
                </div>

                <section className="drawer-section">
                  <div className="drawer-list">
                    {functions.length > 0 ? (
                      functions.map((name) => (
                        <button
                          type="button"
                          key={name}
                          className={`drawer-item ${selectedFunction === name ? "drawer-item-active" : ""}`}
                          onClick={() => setSelectedFunction(name)}
                        >
                          {name}
                        </button>
                      ))
                    ) : (
                      <p className="drawer-empty-line">
                        {selectedFile ? "Loading or no functions found." : "Pick a file first."}
                      </p>
                    )}
                  </div>
                </section>

                <section className="drawer-section">
                  <div className="drawer-section-head">
                    <h3>Flow options</h3>
                    <span>{flowMaxDepth.trim() ? `Depth ${flowMaxDepth.trim()}` : "Unlimited"}</span>
                  </div>

                  <div className="flow-option-group">
                    <label className="field-label" htmlFor="flow-max-depth">
                      Max depth
                    </label>
                    <input
                      id="flow-max-depth"
                      className="path-input flow-depth-input"
                      type="number"
                      min="0"
                      step="1"
                      inputMode="numeric"
                      value={flowMaxDepth}
                      onChange={(event) => setFlowMaxDepth(event.target.value)}
                      placeholder="Unlimited"
                    />
                    <p className="drawer-empty-line">
                      Leave blank to expand the full tree, or set a depth like 2 to stop earlier.
                    </p>
                  </div>

                  <div className="flow-toggle-list" role="group" aria-label="Call type filters">
                    <label className="flow-toggle">
                      <input
                        type="checkbox"
                        checked={includeStdlib}
                        onChange={(event) => setIncludeStdlib(event.target.checked)}
                      />
                      <span>Stdlib calls</span>
                    </label>
                    <label className="flow-toggle">
                      <input
                        type="checkbox"
                        checked={includeExternal}
                        onChange={(event) => setIncludeExternal(event.target.checked)}
                      />
                      <span>External calls</span>
                    </label>
                    <label className="flow-toggle">
                      <input
                        type="checkbox"
                        checked={includeBuiltin}
                        onChange={(event) => setIncludeBuiltin(event.target.checked)}
                      />
                      <span>Builtin calls</span>
                    </label>
                  </div>
                </section>

                <form className="drawer-form" onSubmit={onAnalyzeFunction}>
                  <button className="primary-button full-width" type="submit" disabled={loadingAnalysis}>
                    {loadingAnalysis ? "Analyzing..." : "Analyze Function"}
                  </button>
                </form>
              </div>
            ) : null}

            {activeTab === "node" ? (
              <div className="drawer-panel" role="tabpanel">
                {node ? (
                  <>
                    <div className="details-overview">
                      <p className="details-overview-kicker">Selected node</p>
                      <h3 className="drawer-node-title">{node.label || "Untitled"}</h3>
                      <p className="details-overview-text">{node.summary || "No summary available."}</p>
                    </div>

                    <section className="drawer-section">
                      <div className="drawer-section-head">
                        <h3>Source snippet</h3>
                        <span>{sourceSnippet ? "Code" : "Unavailable"}</span>
                      </div>
                      {sourceSnippet ? (
                        <pre className="source-snippet">
                          <code>{sourceSnippet}</code>
                        </pre>
                      ) : (
                        <p className="drawer-empty-line">No source snippet is available for this node.</p>
                      )}
                    </section>

                    {/* <p className="details-summary">{node.summary || "No summary available for this node."}</p> */}

                    <div className="details-stats">
                      <div className="details-stat">
                        <span>Depth</span>
                        <strong>{node.depth ?? 0}</strong>
                      </div>
                      <div className="details-stat">
                        <span>Children</span>
                        <strong>{node.childCount ?? 0}</strong>
                      </div>
                      <div className="details-stat">
                        <span>Mode</span>
                        <strong>{node.recursive ? "Recursive" : node.truncated ? "Truncated" : "Open"}</strong>
                      </div>
                    </div>

                    <Section
                      title="Project calls"
                      items={callPills}
                      emptyLabel="No project calls were exposed for this node."
                    />
                    <Section title="Stdlib" items={stdlibCalls} emptyLabel="No standard-library calls were exposed." />
                    <Section title="External" items={externalCalls} emptyLabel="No external calls were exposed." />
                    <Section title="Builtins" items={builtinCalls} emptyLabel="No builtin calls were exposed." />
                    <Section title="Decorators" items={decorators} emptyLabel="No decorators were exposed." />
                  </>
                ) : (
                  <div className="drawer-empty-state">
                    <p className="drawer-empty-copy">
                      {hasAnalysis
                        ? "Click a node in the graph to inspect it here."
                        : "Run an analysis first, then click a node to inspect it here."}
                    </p>
                  </div>
                )}
              </div>
            ) : null}
          </div>

          <div className="drawer-footer">
            <div className="drawer-status">
              {error ? <span className="status-pill status-pill-error">{error}</span> : null}
              {loadingDirectory ? <span className="status-pill status-pill-loading">Loading directory...</span> : null}
              {loadingFunctions ? <span className="status-pill status-pill-loading">Loading functions...</span> : null}
              {loadingAnalysis ? <span className="status-pill status-pill-loading">Building graph...</span> : null}
              {!loadingAnalysis && analysis?.tree ? (
                <span className="status-pill status-pill-success">Graph ready</span>
              ) : null}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
