import { FormEvent, useState } from "react";
import { getClient } from "../../api";
import { ApiError } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { SearchResponse } from "../../types/reposcope";

export function SearchPanel({ repositoryId }: { repositoryId: string }) {
  const { focusEvidence } = useWorkspace();
  const [query, setQuery] = useState("");
  const [aware, setAware] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await getClient().search(repositoryId, query.trim(), aware));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="search-query">Relationship-aware retrieval</label>
          <input
            id="search-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. repository boundary validation"
          />
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <input type="checkbox" checked={aware} onChange={(event) => setAware(event.target.checked)} />
          Boost by graph adjacency
        </label>
        <button className="btn" disabled={busy} type="submit">
          {busy ? "Searching…" : "Search"}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div style={{ marginTop: 16 }}>
          {result.results.map((item) => (
            <button
              key={item.sourceId}
              className="search-card"
              onClick={() =>
                focusEvidence(item.fileId, { startLine: item.startLine, endLine: item.endLine }, [item.sourceId])
              }
            >
              <strong>{item.filePath}</strong>
              <div className="meta">
                score {item.score.toFixed(2)} · lexical {item.lexicalScore.toFixed(2)} · graph +
                {item.relationshipBonus.toFixed(2)}
              </div>
              <pre style={{ whiteSpace: "pre-wrap", margin: "8px 0 0", fontFamily: "IBM Plex Mono, monospace", fontSize: 12 }}>
                {item.excerpt}
              </pre>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
