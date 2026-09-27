import type {
  AnalysisJob,
  ChatResponse,
  FileDetail,
  GraphData,
  Repository,
  SearchResponse,
  TreeResponse,
} from "../types/reposcope";
import type { ApiErrorBody } from "../types/reposcope";

export class ApiError extends Error {
  code: string;
  status: number;
  retryable: boolean;
  requestId?: string;

  constructor(message: string, options: { code: string; status: number; retryable?: boolean; requestId?: string }) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.retryable = options.retryable ?? false;
    this.requestId = options.requestId;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return new ApiError(body.error?.message || response.statusText, {
      code: body.error?.code || "HTTP_ERROR",
      status: response.status,
      retryable: body.error?.retryable,
      requestId: body.error?.requestId,
    });
  } catch {
    return new ApiError(response.statusText || "Request failed", {
      code: "HTTP_ERROR",
      status: response.status,
    });
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  listRepositories: () => request<{ repositories: Repository[] }>("/api/repositories"),

  getRepository: (id: string) => request<Repository>(`/api/repositories/${id}`),

  createRepository: (payload: { name: string; sourceType?: string; sourcePath: string }) =>
    request<Repository>("/api/repositories", {
      method: "POST",
      body: JSON.stringify({
        name: payload.name,
        sourceType: payload.sourceType ?? "local_path",
        sourcePath: payload.sourcePath,
      }),
    }),

  analyze: (id: string, force = false) =>
    request<AnalysisJob>(`/api/repositories/${id}/analyze`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),

  getStatus: (id: string) => request<AnalysisJob>(`/api/repositories/${id}/status`),

  getTree: (id: string) => request<TreeResponse>(`/api/repositories/${id}/tree`),

  getFile: (id: string, fileId: string, startLine?: number, endLine?: number) => {
    const params = new URLSearchParams();
    if (startLine != null) params.set("startLine", String(startLine));
    if (endLine != null) params.set("endLine", String(endLine));
    const query = params.toString();
    return request<FileDetail>(`/api/repositories/${id}/files/${fileId}${query ? `?${query}` : ""}`);
  },

  search: (id: string, query: string, relationshipAware = true, limit = 10) =>
    request<SearchResponse>(`/api/repositories/${id}/search`, {
      method: "POST",
      body: JSON.stringify({ query, relationshipAware, limit }),
    }),

  chat: (id: string, question: string) =>
    request<ChatResponse>(`/api/repositories/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  getGraph: (id: string, nodeId?: string, sourceIds?: string[]) => {
    const params = new URLSearchParams();
    if (nodeId) params.set("nodeId", nodeId);
    sourceIds?.forEach((sourceId) => params.append("sourceIds", sourceId));
    const query = params.toString();
    return request<GraphData>(`/api/repositories/${id}/graph${query ? `?${query}` : ""}`);
  },
};
