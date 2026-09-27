import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getClient } from "../api";
import { ApiError } from "../api/client";
import { ChatPanel } from "../components/chat/ChatPanel";
import { FileTree } from "../components/explorer/FileTree";
import { SourceViewer } from "../components/explorer/SourceViewer";
import { GraphVisualizer } from "../components/graph/GraphVisualizer";
import { TopBar } from "../components/layout/TopBar";
import { RepoOverview } from "../components/repo/RepoOverview";
import { SearchPanel } from "../components/search/SearchPanel";
import { WorkspaceProvider, useWorkspace, type WorkspaceTab } from "../context/WorkspaceContext";
import type { AnalysisJob, Repository, TreeNode } from "../types/reposcope";

/**
 * WorkspacePage — Top-level shell that wraps the workspace in its context provider.
 *
 * ``WorkspaceProvider`` supplies the active tab state (graph / code / chat / search)
 * to all child components without prop-drilling.  The actual content is rendered
 * by ``WorkspaceInner`` which has access to the context.
 */
export function WorkspacePage() {
  return (
    <WorkspaceProvider>
      <WorkspaceInner />
    </WorkspaceProvider>
  );
}

/**
 * WorkspaceInner — Three-panel workspace layout for a single repository.
 *
 * Layout:
 *   Left panel   – ``FileTree`` explorer sidebar (scrollable)
 *   Center panel – Tab bar (graph | code | chat | search) + active view
 *   Right panel  – ``RepoOverview`` stats and analysis controls
 *
 * Data fetching:
 *   - On mount: fetches repo metadata, latest job status, and (if READY) file tree.
 *   - While ANALYZING: polls ``/status`` every 1.5 s via ``setInterval``;
 *     the interval is cleared when status leaves ANALYZING.
 *
 * The ``repoId`` path parameter is sourced from React Router’s ``useParams``.
 */
function WorkspaceInner() {
  const { repoId } = useParams();
  const { tab, setTab } = useWorkspace();
  const [repo, setRepo] = useState<Repository | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [error, setError] = useState<string | null>(null);

  /**
   * Refresh callback — fetches the latest repository, job status, and file tree.
   *
   * Memoised with ``useCallback`` on ``repoId`` so the polling ``useEffect``
   * does not re-register the interval on every render.
   */
  const refresh = useCallback(async () => {
    if (!repoId) return;
    const client = getClient();
    const current = await client.getRepository(repoId);
    setRepo(current);
    try {
      setJob(await client.getStatus(repoId));
    } catch {
      setJob(null);
    }
    if (current.status === "READY") {
      const treeResponse = await client.getTree(repoId);
      setTree(treeResponse.tree);
    }
  }, [repoId]);

  useEffect(() => {
    refresh().catch((err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Could not load workspace.");
    });
  }, [refresh]);

  useEffect(() => {
    if (!repoId || repo?.status !== "ANALYZING") return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [repoId, repo?.status, refresh]);

  if (!repoId) return null;

  return (
    <div className="app-shell">
      <TopBar repo={repo ?? undefined} />
      {error ? <p className="error" style={{ padding: 16 }}>{error}</p> : null}
      <div className="workspace">
        {/* Left — file explorer, own vertical scroll */}
        <aside className="panel panel-left">
          <div className="panel-header">Explorer</div>
          <FileTree tree={tree} />
        </aside>

        {/* Center — tabs + graph/code/chat/search */}
        <section className="panel panel-center">
          <div className="tabs">
            {(["graph", "code", "chat", "search"] as WorkspaceTab[]).map((item) => (
              <button key={item} className={`tab ${tab === item ? "active" : ""}`} onClick={() => setTab(item)}>
                {item === "graph" ? "focused graph" : item}
              </button>
            ))}
          </div>
          {tab === "graph" ? (
            <GraphVisualizer repositoryId={repoId} />
          ) : (
            <div className="center-scroll-body">
              <div className="center-body">
                {tab === "code" ? <SourceViewer repositoryId={repoId} /> : null}
                {tab === "chat" ? <ChatPanel repositoryId={repoId} /> : null}
                {tab === "search" ? <SearchPanel repositoryId={repoId} /> : null}
              </div>
            </div>
          )}
        </section>

        {/* Right — repo overview, own vertical scroll, no horizontal */}
        <aside className="panel panel-right">
          <div className="panel-header">Discoveries &amp; Stats</div>
          <div className="panel-right-body">
            {repo ? <RepoOverview repo={repo} job={job} onRefresh={() => void refresh()} /> : null}
          </div>
        </aside>
      </div>
    </div>
  );
}
