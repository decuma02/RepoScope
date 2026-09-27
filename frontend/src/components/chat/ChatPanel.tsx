import { FormEvent, useState } from "react";
import { getClient } from "../../api";
import { ApiError } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { ChatResponse } from "../../types/reposcope";

const GOLDEN = [
  "What are this repository's major components, and how do they relate?",
  "What depends on the repository boundary validator?",
  "Where is grounded chat implemented, and what else is involved?",
];

export function ChatPanel({ repositoryId }: { repositoryId: string }) {
  const { focusEvidence, setGraphSourceIds, setGraphNodeId } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Array<{ q: string; a?: ChatResponse }>>([]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    setQuestion("");
    setHistory((prev) => [...prev, { q: trimmed }]);
    try {
      const response = await getClient().chat(repositoryId, trimmed);
      setHistory((prev) => {
        const next = [...prev];
        next[next.length - 1] = { q: trimmed, a: response };
        return next;
      });
      setGraphSourceIds(response.sources.map((source) => source.sourceId));
      if (response.graphFocus.nodeIds[0]) setGraphNodeId(response.graphFocus.nodeIds[0]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Chat request failed.");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <div>
      <div className="chip-row">
        {GOLDEN.map((item) => (
          <button key={item} className="chip" type="button" onClick={() => void ask(item)}>
            {item}
          </button>
        ))}
      </div>
      <div className="messages">
        {history.length === 0 ? (
          <p className="meta">Ask a grounded question. Every answer is tied to file and line evidence.</p>
        ) : null}
        {history.map((turn, index) => (
          <div key={`${turn.q}-${index}`}>
            <div className="bubble user">{turn.q}</div>
            {turn.a ? (
              <div className="bubble assistant">
                <span className={`badge ${turn.a.confidence}`} style={{ marginBottom: 8 }}>
                  {turn.a.confidence}
                </span>
                <div>{turn.a.answer}</div>
                {turn.a.sources.length ? (
                  <div style={{ marginTop: 12 }}>
                    <div className="meta">Sources</div>
                    {turn.a.sources.map((source) => (
                      <button
                        key={source.sourceId}
                        className="source-card"
                        onClick={() =>
                          focusEvidence(source.fileId, { startLine: source.startLine, endLine: source.endLine }, [
                            ...turn.a!.graphFocus.nodeIds,
                            source.sourceId,
                          ])
                        }
                      >
                        <strong>{source.filePath}</strong>
                        <div className="meta">
                          L{source.startLine}–{source.endLine}
                          {source.componentName ? ` · ${source.componentName}` : ""} · {source.reason}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : null}
                {turn.a.relationshipEvidence.length ? (
                  <div style={{ marginTop: 8 }}>
                    <div className="meta">Relationship evidence</div>
                    {turn.a.relationshipEvidence.map((rel) => (
                      <div key={rel.relationshipId} className="meta">
                        {rel.sourcePath} —{rel.type}→ {rel.targetPath} ({Math.round(rel.confidence * 100)}%)
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="bubble assistant meta">Retrieving grounded context…</div>
            )}
          </div>
        ))}
      </div>
      {error ? <p className="error">{error}</p> : null}
      <form onSubmit={onSubmit} style={{ display: "flex", gap: 8 }}>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about this repository…"
          disabled={busy}
        />
        <button className="btn" disabled={busy} type="submit">
          Ask
        </button>
      </form>
    </div>
  );
}
