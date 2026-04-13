import { useEffect, useRef } from "react";

function toTitle(value) {
  return String(value ?? "")
    .replace(/^[a-z]/, (char) => char.toUpperCase())
    .trim();
}

export function SearchPalette({ open, query, results, onQueryChange, onClose, onPick }) {
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      inputRef.current?.select?.();
    }
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="search-palette-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section className="search-palette" role="dialog" aria-modal="true" aria-label="Search workspace">
        <form
          className="search-palette-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (results[0]) {
              onPick(results[0]);
            }
          }}
        >
          <input
            ref={inputRef}
            className="search-palette-input"
            type="text"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search functions, files, symbols, phrases"
            spellCheck={false}
            autoComplete="off"
          />
          <button className="search-palette-close" type="button" onClick={onClose}>
            Esc
          </button>
        </form>

        <div className="search-palette-results">
          {query.trim() ? (
            results.length > 0 ? (
              results.map((result) => (
                <button
                  key={result.id}
                  type="button"
                  className="search-palette-item"
                  onClick={() => onPick(result)}
                >
                  <span className="search-palette-item-main">
                    <strong>{result.title}</strong>
                    <span>{toTitle(result.type)}</span>
                  </span>
                  <span className="search-palette-item-subtitle">{result.subtitle}</span>
                </button>
              ))
            ) : (
              <p className="search-palette-empty">No matches found.</p>
            )
          ) : (
            <p className="search-palette-empty">Type to search the current workspace.</p>
          )}
        </div>
      </section>
    </div>
  );
}
