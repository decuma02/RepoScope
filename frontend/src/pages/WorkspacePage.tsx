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

export function WorkspacePage() {
  return (
    <WorkspaceProvider>
      <WorkspaceInner />
    </WorkspaceProvider>
  );
}

function WorkspaceInner() {
  const { repoId } = useParams();
  const { tab, setTab } = useWorkspace();
  const [repo, setRepo] = useState<Repository | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [error, setError] = useState<string | null>(null);

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
