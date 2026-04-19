import { Handle, Position } from "reactflow";

export function AnalysisNode({ data, selected }) {
  const calls = Array.isArray(data?.calls) ? data.calls : [];
  const summary = String(data?.summary ?? "").trim();
  const role = String(data?.role ?? "function");
  const roleLabel = String(data?.roleLabel ?? role);
  const roleGlyph = String(data?.roleGlyph ?? "●");
  const kind = String(data?.kind ?? "");
  const collapsedCount = Number(data?.collapsedCount ?? 0);
  const collapseReason = String(data?.collapseReason ?? "").trim();
  const isCluster = kind === "cluster" || collapsedCount > 0;
  const hiddenChildCount = Number(data?.hiddenChildCount ?? 0);
  const canToggleExpand = Boolean(data?.canToggleExpand);
  const isExpanded = Boolean(data?.expanded);
  const badges = [];

  if (data?.depth === 0) {
    badges.push("root");
  }
  if (isCluster) {
    badges.push(`collapsed ${collapsedCount || calls.length}`);
  }
  if (data?.recursive) {
    badges.push("recursive");
  }
  if (data?.truncated) {
    badges.push("truncated");
  }

  const callCountLabel = isCluster
    ? `${collapsedCount || calls.length} hidden`
    : `${calls.length} call${calls.length === 1 ? "" : "s"}`;
  const toggleLabel = hiddenChildCount > 0 ? `Expand +${hiddenChildCount}` : "Collapse";

  return (
    <div
      className={`analysis-node-card ${selected ? "analysis-node-card-selected" : ""}`}
      data-role={role}
      data-kind={kind || "function"}
      title={summary || String(data?.label ?? "Untitled")}
      aria-label={`${String(data?.label ?? "Untitled")}: ${summary || "No summary available."}`}
    >
      <Handle type="target" position={Position.Top} className="analysis-node-handle analysis-node-handle-target" />
      <Handle
        type="source"
        position={Position.Bottom}
        className="analysis-node-handle analysis-node-handle-source"
      />
      <div className="analysis-node-accent" aria-hidden="true" />
      <div className="analysis-node-orb" />
      <div className="analysis-node-topline">
        <div className="analysis-node-titlewrap">
          <span className={`analysis-node-role analysis-node-role-${role}`}>
            <span className="analysis-node-role-glyph">{roleGlyph}</span>
            {roleLabel}
          </span>
          <span className="analysis-node-name" title={String(data?.label ?? "Untitled")}>
            {data?.label}
          </span>
        </div>
        <div className="analysis-node-actions">
          <span className="analysis-node-count">{callCountLabel}</span>
          {canToggleExpand ? (
            <button
              type="button"
              className={`analysis-node-expand-button ${isExpanded ? "analysis-node-expand-button-open" : ""}`}
              title={toggleLabel}
              aria-label={toggleLabel}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                if (typeof data?.onToggleExpand === "function") {
                  data.onToggleExpand();
                }
              }}
            >
              {hiddenChildCount > 0 ? `+${hiddenChildCount}` : "−"}
            </button>
          ) : null}
        </div>
      </div>

      {summary ? (
        <p className="analysis-node-summary" title={summary}>
          {summary}
        </p>
      ) : (
        <p className="analysis-node-summary analysis-node-summary-empty">No summary available.</p>
      )}

      {isCluster && collapseReason ? (
        <p className="analysis-node-cluster-note" title={collapseReason}>
          {collapseReason}
        </p>
      ) : null}

      <div className="analysis-node-footer">
        <span className="analysis-node-depth">Depth {data?.depth ?? 0}</span>
        <div className="analysis-node-badges">
          {badges.map((badge) => (
            <span key={badge} className="analysis-node-badge">
              {badge}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
