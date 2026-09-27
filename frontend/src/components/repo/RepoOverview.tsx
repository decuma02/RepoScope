import { useState } from "react";
import { getClient } from "../../api";
import { ApiError } from "../../api/client";
import type { AnalysisJob, Repository } from "../../types/reposcope";

export function RepoOverview({
  repo,
  job,
  onRefresh,
}: {
  repo: Repository;
  job?: AnalysisJob | null;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze(force: boolean) {
    setBusy(true);
    setError(null);
    try {
      await getClient().analyze(repo.id, force);
      onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analysis failed to start.");
    } finally {
      setBusy(false);
    }
  }

  const progress = job?.progress ?? (repo.status === "READY" ? 1 : 0);

  return (
    <div>
      <p className="meta" style={{ marginTop: 0 }}>
        {repo.rootLabel || repo.name} · {repo.sourceType}
      </p>
      <div className="stats">
        <div className="stat">
          <b>{repo.counts.filesDiscovered}</b>
          <span>Discovered</span>
        </div>
        <div className="stat">
          <b>{repo.counts.filesAnalyzed}</b>
          <span>Analyzed</span>
        </div>
        <div className="stat">
          <b>{repo.counts.filesSkipped}</b>
          <span>Skipped</span>
        </div>
        <div className="stat">
          <b>{repo.counts.componentsFound}</b>
          <span>Components</span>
        </div>
        <div className="stat">
          <b>{repo.counts.relationshipsFound}</b>
          <span>Relationships</span>
        </div>
      </div>
      <div className="progress">
        <div style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      <p className="meta">
        Stage: {job?.stage || repo.status}
        {job?.warnings?.length ? ` · ${job.warnings.length} warning(s)` : ""}
      </p>
      {job?.error || repo.status === "FAILED" ? <p className="error">{job?.error || "Analysis failed."}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button className="btn" disabled={busy || repo.status === "ANALYZING"} onClick={() => void analyze(false)}>
          {repo.status === "ANALYZING" ? "Analyzing…" : "Analyze"}
        </button>
        <button className="btn secondary" disabled={busy} onClick={() => void analyze(true)}>
          Re-analyze
        </button>
      </div>
    </div>
  );
}
