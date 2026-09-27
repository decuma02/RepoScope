import treeFixture from "../fixtures/repository_tree.json";
import graphFixture from "../fixtures/graph_data.json";
import chatFixture from "../fixtures/chat_response.json";
import searchFixture from "../fixtures/search_results.json";
import componentsFixture from "../fixtures/components.json";
import type {
  AnalysisJob,
  ChatResponse,
  Component,
  FileDetail,
  GraphData,
  Repository,
  SearchResponse,
  TreeResponse,
} from "../types/reposcope";
import { api } from "./client";

const DEMO_REPO: Repository = {
  id: "repo_demo",
  name: "RepoScope Demo",
  sourceType: "local_path",
  sourcePath: "/demo/reposcope",
  rootLabel: "RepoScope",
  status: "READY",
  createdAt: "2026-03-20T10:00:00Z",
  analyzedAt: "2026-03-20T10:01:00Z",
  counts: {
    filesDiscovered: 2,
    filesAnalyzed: 2,
    filesSkipped: 0,
    componentsFound: 2,
    relationshipsFound: 1,
  },
};

const DEMO_JOB: AnalysisJob = {
  id: "job_demo",
  repositoryId: "repo_demo",
  status: "READY",
  progress: 1,
  stage: "complete",
  filesDiscovered: 2,
  filesAnalyzed: 2,
  filesSkipped: 0,
  componentsFound: 2,
  relationshipsFound: 1,
  warnings: [],
  startedAt: "2026-03-20T10:00:30Z",
  completedAt: "2026-03-20T10:01:00Z",
};

const FILE_EXCERPTS: Record<string, string> = {
  file_boundary: `class RepositoryBoundaryValidator:
    @staticmethod
    def validate_repository_root(path_str: str) -> str:
        """Ensure all filesystem access stays inside the registered root."""
        resolved = Path(path_str).resolve()
        return str(resolved)
`,
  file_main: `from fastapi import FastAPI
from backend.app.storage.boundary import RepositoryBoundaryValidator

app = FastAPI(title="RepoScope")

@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR"}})
`,
};

function delay<T>(value: T, ms = 180): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

const mockRepos: Repository[] = [{ ...DEMO_REPO }];

export const mockApi: typeof api = {
  listRepositories: () => delay({ repositories: mockRepos.map((repo) => ({ ...repo })) }),

  getRepository: async (id: string) => {
    const repo = mockRepos.find((item) => item.id === id) ?? DEMO_REPO;
    return delay({ ...repo, id });
  },

  createRepository: async (payload) => {
    const repo: Repository = {
      ...DEMO_REPO,
      id: `repo_${Date.now()}`,
      name: payload.name,
      sourcePath: payload.sourcePath || payload.githubUrl || "/demo/github",
      sourceType: payload.sourceType ?? "local_path",
      status: "CREATED",
      analyzedAt: undefined,
      createdAt: new Date().toISOString(),
    };
    mockRepos.unshift(repo);
    return delay(repo);
  },

  analyze: async (id: string) => delay({ ...DEMO_JOB, repositoryId: id, status: "READY" }),

  getStatus: async (id: string) => delay({ ...DEMO_JOB, repositoryId: id }),

  getTree: async (id: string) => delay({ ...(treeFixture as TreeResponse), repositoryId: id }),

  getFile: async (id: string, fileId: string) => {
    const components = (componentsFixture.components as Component[]).filter((item) => item.fileId === fileId);
    const node = findNode((treeFixture as TreeResponse).tree, fileId);
    const detail: FileDetail = {
      id: fileId,
      repositoryId: id,
      path: node?.path ?? fileId,
      language: node?.language ?? "python",
      extension: ".py",
      sizeBytes: node?.sizeBytes ?? 0,
      status: "analyzed",
      components,
      excerpt: FILE_EXCERPTS[fileId] ?? "No excerpt available in demo fixtures.",
      startLine: 1,
      endLine: (FILE_EXCERPTS[fileId] ?? "").split("\n").length,
    };
    return delay(detail);
  },

  search: async () => delay(searchFixture as SearchResponse),

  chat: async (_id: string, question: string) =>
    delay({
      ...(chatFixture as ChatResponse),
      answer: `Demo answer for “${question}”. ${chatFixture.answer}`,
    }),

  getGraph: async (_id: string, nodeId?: string) => {
    const graph = structuredClone(graphFixture) as GraphData;
    graph.nodes = graph.nodes.map((node) => ({
      ...node,
      selected: nodeId ? node.id === nodeId : Boolean(node.selected),
    }));
    if (nodeId) {
      graph.focus = { type: "file", id: nodeId };
    }
    return delay(graph);
  },
};

function findNode(nodes: TreeResponse["tree"], id: string): TreeResponse["tree"][number] | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const match = findNode(node.children, id);
      if (match) return match;
    }
  }
  return undefined;
}
