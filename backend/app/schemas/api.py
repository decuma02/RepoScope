from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.app.models.domain import RepositoryStatus, RelationshipType, ComponentType

# --- Standard Error Format ---
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    retryable: bool = False
    requestId: str

class ErrorResponse(BaseModel):
    error: ErrorDetail

# --- Repository Schemas ---
class RepositoryCreateRequest(BaseModel):
    name: str = Field(..., description="Human-readable repository name")
    sourceType: str = Field("local_path", description="Source type, e.g. local_path")
    sourcePath: str = Field(..., description="Absolute filesystem path to repository root")

class RepositoryCountsDTO(BaseModel):
    filesDiscovered: int = 0
    filesAnalyzed: int = 0
    filesSkipped: int = 0
    componentsFound: int = 0
    relationshipsFound: int = 0

class RepositoryResponse(BaseModel):
    id: str
    name: str
    sourceType: str
    sourcePath: str
    rootLabel: Optional[str] = None
    status: RepositoryStatus
    createdAt: str
    analyzedAt: Optional[str] = None
    counts: RepositoryCountsDTO

class RepositoryListResponse(BaseModel):
    repositories: List[RepositoryResponse]

# --- Analysis Schemas ---
class AnalysisTriggerRequest(BaseModel):
    force: Optional[bool] = False

class AnalysisJobResponse(BaseModel):
    id: str
    repositoryId: str
    status: RepositoryStatus
    progress: float
    stage: str
    filesDiscovered: int
    filesAnalyzed: int
    filesSkipped: int
    componentsFound: int
    relationshipsFound: int
    warnings: List[str] = []
    error: Optional[str] = None
    startedAt: str
    completedAt: Optional[str] = None

# --- Tree & File Detail Schemas ---
class TreeNodeDTO(BaseModel):
    id: str
    name: str
    path: str
    isDir: bool
    language: Optional[str] = None
    sizeBytes: Optional[int] = 0
    children: Optional[List['TreeNodeDTO']] = None

class TreeResponse(BaseModel):
    repositoryId: str
    tree: List[TreeNodeDTO]

class ComponentDTO(BaseModel):
    id: str
    fileId: str
    name: str
    type: ComponentType
    startLine: int
    endLine: int
    signature: Optional[str] = None
    summary: Optional[str] = None

class ComponentListResponse(BaseModel):
    repositoryId: str
    components: List[ComponentDTO]

class RelationshipDTO(BaseModel):
    id: str
    repositoryId: str
    sourceType: str
    sourceId: str
    targetType: str
    targetId: str
    type: RelationshipType
    confidence: float
    sourceLine: Optional[int] = None
    evidence: Optional[str] = None

class RelationshipListResponse(BaseModel):
    repositoryId: str
    relationships: List[RelationshipDTO]

class FileDetailResponse(BaseModel):
    id: str
    repositoryId: str
    path: str
    language: Optional[str] = None
    extension: Optional[str] = None
    sizeBytes: int
    status: str
    components: List[ComponentDTO] = []
    excerpt: Optional[str] = None
    startLine: Optional[int] = 1
    endLine: Optional[int] = None

# --- Search / Retrieval Schemas ---
class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10
    relationshipAware: Optional[bool] = True

class SearchResultItem(BaseModel):
    sourceId: str
    fileId: str
    filePath: str
    componentName: Optional[str] = None
    score: float
    lexicalScore: float
    relationshipBonus: float
    startLine: int
    endLine: int
    excerpt: str
    relevanceReason: str

class RelationshipEvidenceItem(BaseModel):
    relationshipId: str
    sourcePath: str
    targetPath: str
    type: RelationshipType
    confidence: float
    sourceLine: Optional[int] = None

class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    relationships: List[RelationshipEvidenceItem] = []

class RetrievalComparisonResponse(BaseModel):
    query: str
    relationshipAwareResults: List[SearchResultItem]
    textOnlyBaselineResults: List[SearchResultItem]
    graphExpandedFilesCount: int
    differentiationSummary: str

# --- AI Chat & Context Schemas ---
class ChatRequest(BaseModel):
    question: str

class SourceReference(BaseModel):
    sourceId: str
    fileId: str
    filePath: str
    componentId: Optional[str] = None
    componentName: Optional[str] = None
    startLine: int
    endLine: int
    snippet: Optional[str] = None
    reason: str
    relevance: float = 1.0

class GraphFocusDTO(BaseModel):
    nodeIds: List[str] = []

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceReference] = []
    relationshipEvidence: List[RelationshipEvidenceItem] = []
    graphFocus: GraphFocusDTO
    confidence: str = "supported"

# --- Graph Schemas ---
class GraphNode(BaseModel):
    id: str
    type: str  # file or component
    label: str
    path: str
    selected: bool = False

class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: RelationshipType
    confidence: float = 1.0

class GraphResponse(BaseModel):
    focus: Optional[Dict[str, Any]] = None
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
