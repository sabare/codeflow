function normalizeList(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))];
}

function Section({ title, items, emptyLabel }) {
  return (
    <section className="details-section">
      <div className="details-section-head">
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
        <p className="details-empty-line">{emptyLabel}</p>
      )}
    </section>
  );
}

function SummaryBlock({ analysis }) {
  if (!analysis?.tree?.summary) {
    return null;
  }

  return (
    <div className="details-overview">
      <p className="details-overview-kicker">Project overview</p>
      <p className="details-overview-text">{analysis.tree.summary}</p>
    </div>
  );
}

export function DetailsPanel({ node, analysis, isLoading }) {
  if (!node) {
    return (
      <aside className="workspace-panel details-panel">
        <div className="panel-head">
          <div>
            <p className="panel-kicker">Details</p>
            <h2>{isLoading ? "Preparing graph" : "No node selected"}</h2>
          </div>
        </div>

        <div className="details-empty-state">
          <SummaryBlock analysis={analysis} />
          <p className="details-empty-copy">
            {isLoading
              ? "We are generating the graph now. Once it loads, click a node to inspect it."
              : "Click a node in the graph to pin its summary, direct calls, and metadata here."}
          </p>
          <div className="details-tips">
            <span>1. Analyze a folder path</span>
            <span>2. Zoom and pan the graph</span>
            <span>3. Click any node for details</span>
          </div>
        </div>
      </aside>
    );
  }

  const directCalls = normalizeList(node.data?.calls);
  const projectCalls = normalizeList(node.data?.projectCalls);
  const stdlibCalls = normalizeList(node.data?.stdlibCalls);
  const externalCalls = normalizeList(node.data?.externalCalls);
  const builtinCalls = normalizeList(node.data?.builtinCalls);
  const decorators = normalizeList(node.data?.decorators);
  const callPills = projectCalls.length > 0 ? projectCalls : directCalls;

  return (
    <aside className="workspace-panel details-panel">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">Details</p>
          <h2>{node.data?.label ?? "Untitled"}</h2>
        </div>
        <div className="panel-chip">Depth {node.data?.depth ?? 0}</div>
      </div>

      <SummaryBlock analysis={analysis} />

      <p className="details-summary">
        {String(node.data?.summary ?? "").trim() || "No summary available for this node."}
      </p>

      <div className="details-stats">
        <div className="details-stat">
          <span>Direct calls</span>
          <strong>{callPills.length}</strong>
        </div>
        <div className="details-stat">
          <span>Children</span>
          <strong>{node.data?.childCount ?? 0}</strong>
        </div>
        <div className="details-stat">
          <span>Type</span>
          <strong>{node.data?.recursive ? "Recursive" : node.data?.truncated ? "Truncated" : "Open"}</strong>
        </div>
      </div>

      <Section
        title="Project calls"
        items={callPills}
        emptyLabel="No project calls were exposed for this node."
      />
      <Section
        title="Stdlib"
        items={stdlibCalls}
        emptyLabel="No standard-library calls were exposed."
      />
      <Section
        title="External"
        items={externalCalls}
        emptyLabel="No external calls were exposed."
      />
      <Section
        title="Builtins"
        items={builtinCalls}
        emptyLabel="No builtin calls were exposed."
      />
      <Section
        title="Decorators"
        items={decorators}
        emptyLabel="No decorators were exposed."
      />
    </aside>
  );
}
