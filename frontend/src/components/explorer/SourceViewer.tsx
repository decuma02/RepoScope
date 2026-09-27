import { useEffect, useState } from "react";
import { getClient } from "../../api";
import { ApiError } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { FileDetail } from "../../types/reposcope";

export function SourceViewer({ repositoryId }: { repositoryId: string }) {
  const { selectedFileId, highlight, setHighlight, setGraphNodeId } = useWorkspace();
  const [file, setFile] = useState<FileDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedFileId) {
      setFile(null);
      return;
    }
    let cancelled = false;
    getClient()
      .getFile(repositoryId, selectedFileId, highlight?.startLine, highlight?.endLine)
      .then((detail) => {
        if (!cancelled) {
          setFile(detail);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load file.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repositoryId, selectedFileId, highlight?.startLine, highlight?.endLine]);

  if (!selectedFileId) {
    return <p className="meta">Select a file in the explorer, or open a source from chat or search.</p>;
  }
  if (error) return <p className="error">{error}</p>;
  if (!file) return <p className="meta">Loading source…</p>;

  const lines = (file.excerpt || "").split("\n");
  const start = file.startLine ?? 1;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
        <div>
          <strong>{file.path}</strong>
          <div className="meta">
            {file.language || "unknown"} · {file.sizeBytes} bytes
          </div>
        </div>
      </div>
      {file.components.length ? (
        <div className="components">
          {file.components.map((component) => (
            <button
              key={component.id}
              className="component-pill"
              onClick={() => {
                setHighlight({ startLine: component.startLine, endLine: component.endLine });
                setGraphNodeId(component.id);
              }}
            >
              {component.type} {component.name}
            </button>
          ))}
        </div>
      ) : null}
      <div className="source-view">
        {lines.map((line, index) => {
          const lineNo = start + index;
          const active = highlight && lineNo >= highlight.startLine && lineNo <= highlight.endLine;
          return (
            <div className={`source-line ${active ? "highlight" : ""}`} key={lineNo}>
              <span className="ln">{lineNo}</span>
              <pre>{line || " "}</pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}
