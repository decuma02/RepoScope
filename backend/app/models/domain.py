"""
domain.py — Core domain models for RepoScope.

Defines the canonical enumerations and dataclasses that represent the
fundamental entities persisted in the SQLite database:
  - RepositoryStatus  : lifecycle state of a repository registration
  - RelationshipType  : edge type in the code relationship graph
  - ComponentType     : kind of code symbol (function, class, endpoint, etc.)
  - RepositoryEntity  : a registered repository record
  - FileEntity        : a source file belonging to a repository
  - ComponentEntity   : a named code symbol extracted from a file
  - RelationshipEntity: a directed edge between two code entities

These types are shared across the service layer, storage layer, and API
schemas (which use Pydantic counterparts backed by these enums).
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class RepositoryStatus(str, Enum):
    """Lifecycle state of a repository within RepoScope.

    Transitions:
        CREATED   → ANALYZING  (when analysis is triggered)
        ANALYZING → READY      (on successful pipeline completion)
        ANALYZING → FAILED     (on unrecoverable pipeline error)
    """
    CREATED   = "CREATED"    # Registered but not yet analysed
    ANALYZING = "ANALYZING"  # Analysis pipeline actively running
    READY     = "READY"      # Analysis complete; all features available
    FAILED    = "FAILED"     # Analysis pipeline encountered a fatal error


class RelationshipType(str, Enum):
    """Directed edge type in the code dependency graph.

    IMPORTS  – file/module A statically imports from file/module B.
    EXPORTS  – a symbol in A is re-exported and consumed by B.
    USES     – a component in A calls or references a component in B.
    """
    IMPORTS = "IMPORTS"
    EXPORTS = "EXPORTS"
    USES    = "USES"


class ComponentType(str, Enum):
    """Granularity / kind of a code symbol extracted by the structure extractor.

    FUNCTION  – a standalone function definition.
    METHOD    – a function defined inside a class body.
    CLASS     – a class or interface declaration.
    MODULE    – the top-level module scope of a file.
    ENDPOINT  – a web framework route handler (FastAPI, Express, etc.).
    DIRECTORY – a synthetic node representing a directory in the file tree.
    """
    FUNCTION  = "function"
    METHOD    = "method"
    CLASS     = "class"
    MODULE    = "module"
    ENDPOINT  = "endpoint"
    DIRECTORY = "directory"


@dataclass
class RepositoryCounts:
    """Aggregate counters for a repository's ingestion and analysis results."""
    filesDiscovered:   int = 0  # Total files found during discovery walk
    filesAnalyzed:     int = 0  # Files successfully parsed and stored
    filesSkipped:      int = 0  # Files ignored (binary, too large, excluded)
    componentsFound:   int = 0  # Named code symbols extracted
    relationshipsFound:int = 0  # Directed dependency edges identified


@dataclass
class RepositoryEntity:
    """In-memory representation of a repository row from the ``repositories`` table."""
    id:         str              # Unique identifier, e.g. "repo_abc123"
    name:       str              # Human-readable display name
    sourceType: str              # "local_path" or "github"
    sourcePath: str              # Absolute path on the analysis server
    status:     RepositoryStatus
    createdAt:  str              # ISO-8601 UTC timestamp
    rootLabel:  Optional[str] = None  # Display label for the root tree node
    analyzedAt: Optional[str] = None  # ISO-8601 UTC timestamp of last analysis
    counts:     RepositoryCounts = field(default_factory=RepositoryCounts)


@dataclass
class FileEntity:
    """In-memory representation of a source file row from the ``files`` table."""
    id:           str
    repositoryId: str
    path:         str            # Relative path from the repository root
    language:     Optional[str] = None   # Inferred language (e.g. "py", "ts")
    extension:    Optional[str] = None   # Raw file extension (e.g. ".py")
    sizeBytes:    int = 0
    contentHash:  Optional[str] = None   # Reserved for future change detection
    status:       str = "READY"


@dataclass
class ComponentEntity:
    """In-memory representation of a code symbol extracted from a file."""
    id:           str
    fileId:       str
    repositoryId: str
    name:         str
    type:         ComponentType
    startLine:    int   # 1-indexed, inclusive
    endLine:      int   # 1-indexed, inclusive
    signature:    Optional[str] = None  # Full parameter/return signature
    summary:      Optional[str] = None  # Short natural-language description
    isExported:   bool = False          # Whether the symbol is publicly exported
    parentName:   Optional[str] = None  # Enclosing class name for methods


@dataclass
class RelationshipEntity:
    """In-memory representation of a directed dependency edge."""
    id:           str
    repositoryId: str
    sourceType:   str   # "file" or "component"
    sourceId:     str   # ID of the source file or component
    targetType:   str   # "file" or "component"
    targetId:     str   # ID of the target file or component
    type:         RelationshipType
    confidence:   float = 1.0           # Extraction confidence [0, 1]
    sourceLine:   Optional[int] = None  # Line number of the import/call site
    evidence:     Optional[str] = None  # Raw import string or call expression

