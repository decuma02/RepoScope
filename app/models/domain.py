from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

class RepositoryStatus(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    READY = "READY"
    FAILED = "FAILED"

class RelationshipType(str, Enum):
    IMPORTS = "IMPORTS"
    EXPORTS = "EXPORTS"
    USES = "USES"

class ComponentType(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    ENDPOINT = "endpoint"

@dataclass
class RepositoryCounts:
    filesDiscovered: int = 0
    filesAnalyzed: int = 0
    filesSkipped: int = 0
    componentsFound: int = 0
    relationshipsFound: int = 0

@dataclass
class RepositoryEntity:
    id: str
    name: str
    sourceType: str
    sourcePath: str
    status: RepositoryStatus
    createdAt: str
    rootLabel: Optional[str] = None
    analyzedAt: Optional[str] = None
    counts: RepositoryCounts = field(default_factory=RepositoryCounts)

@dataclass
class FileEntity:
    id: str
    repositoryId: str
    path: str
    language: Optional[str] = None
    extension: Optional[str] = None
    sizeBytes: int = 0
    contentHash: Optional[str] = None
    status: str = "READY"

@dataclass
class ComponentEntity:
    id: str
    fileId: str
    repositoryId: str
    name: str
    type: ComponentType
    startLine: int
    endLine: int
    signature: Optional[str] = None
    summary: Optional[str] = None

@dataclass
class RelationshipEntity:
    id: str
    repositoryId: str
    sourceType: str
    sourceId: str
    targetType: str
    targetId: str
    type: RelationshipType
    confidence: float = 1.0
    sourceLine: Optional[int] = None
    evidence: Optional[str] = None
