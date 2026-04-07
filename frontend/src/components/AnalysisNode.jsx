import { Handle, Position } from "reactflow";

export function AnalysisNode({ data, selected }) {
  const calls = Array.isArray(data?.calls) ? data.calls : [];
  const summary = String(data?.summary ?? "").trim();
  const role = String(data?.role ?? "function");
  const roleLabel = String(data?.roleLabel ?? role);
  const roleGlyph = String(data?.roleGlyph ?? "●");
  const badges = [];

  if (data?.depth === 0) {
    badges.push("root");
  }
  if (data?.recursive) {
    badges.push("recursive");
  }
  if (data?.truncated) {
    badges.push("truncated");
  }

  return (
    <div
      className={`analysis-node-card ${selected ? "analysis-node-card-selected" : ""}`}
      data-role={role}
      title={summary || String(data?.label ?? "Untitled")}
      aria-label={`${String(data?.label ?? "Untitled")}: ${summary || "No summary available."}`}
    >
      <Handle type="target" position={Position.Top} className="analysis-node-handle analysis-node-handle-target" />
      <Handle
        type="source"
        position={Position.Bottom}
        className="analysis-node-handle analysis-node-handle-source"
      />
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
        <span className="analysis-node-count">
          {calls.length} call{calls.length === 1 ? "" : "s"}
        </span>
      </div>

      {summary ? (
        <p className="analysis-node-summary" title={summary}>
          {summary}
        </p>
      ) : (
        <p className="analysis-node-summary analysis-node-summary-empty">No summary available.</p>
      )}

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
