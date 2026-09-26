// RepoScope Shared Frontend TypeScript Data Contracts

export type RepositoryStatus = "CREATED" | "ANALYZING" | "READY" | "FAILED";
export type RelationshipType = "IMPORTS" | "EXPORTS" | "USES";
export type ComponentType = "function" | "class" | "module" | "endpoint";

export interface RepositoryCounts {
  filesDiscovered: number;
  filesAnalyzed: number;
  filesSkipped: number;
  componentsFound: number;
  relationshipsFound: number;
}

export interface Repository {
  id: string;
  name: string;
  sourceType: string;
  sourcePath: string;
  rootLabel?: string;
  status: RepositoryStatus;
  createdAt: string;
  analyzedAt?: string;
  counts: RepositoryCounts;
}

export interface AnalysisJob {
  id: string;
  repositoryId: string;
  status: RepositoryStatus;
  progress: number;
  stage: string;
  filesDiscovered: number;
  filesAnalyzed: number;
  filesSkipped: number;
  componentsFound: number;
  relationshipsFound: number;
  warnings: string[];
  error?: string;
  startedAt: string;
  completedAt?: string;
}

export interface TreeNode {
  id: string;
  name: string;
  path: string;
  isDir: boolean;
  language?: string;
  sizeBytes?: number;
  children?: TreeNode[];
}

export interface Component {
  id: string;
  fileId: string;
  name: string;
  type: ComponentType;
  startLine: number;
  endLine: number;
  signature?: string;
  summary?: string;
}

export interface Relationship {
  id: string;
  repositoryId: string;
  sourceType: string;
  sourceId: string;
  targetType: string;
  targetId: string;
  type: RelationshipType;
  confidence: number;
  sourceLine?: number;
  evidence?: string;
}

export interface SearchResultItem {
  sourceId: string;
  fileId: string;
  filePath: string;
  componentName?: string;
  score: number;
  lexicalScore: number;
  relationshipBonus: number;
  startLine: number;
  endLine: number;
  excerpt: string;
  relevanceReason: string;
}

export interface SourceEvidence {
  sourceId: string;
  fileId: string;
  filePath: string;
  componentId?: string;
  componentName?: string;
  startLine: number;
  endLine: number;
  snippet?: string;
  reason: string;
  relevance: number;
}

export interface ContextPackage {
  query: string;
  repositoryName: string;
  context: Array<{
    sourceId: string;
    filePath: string;
    startLine: number;
    endLine: number;
    content: string;
  }>;
  relationships: Array<{
    relationshipId: string;
    source: string;
    target: string;
    type: RelationshipType;
  }>;
  tokenEstimate: number;
}

export interface ChatResponse {
  answer: string;
  sources: SourceEvidence[];
  relationshipEvidence: Array<{
    relationshipId: string;
    sourcePath: string;
    targetPath: string;
    type: RelationshipType;
    confidence: number;
    sourceLine?: number;
  }>;
  graphFocus: {
    nodeIds: string[];
  };
  confidence: "supported" | "insufficient_evidence" | "failed";
}

export interface GraphNode {
  id: string;
  type: "file" | "component";
  label: string;
  path: string;
  selected?: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: RelationshipType;
  confidence: number;
}

export interface GraphData {
  focus?: {
    type: string;
    id: string;
  };
  nodes: GraphNode[];
  edges: GraphEdge[];
}
