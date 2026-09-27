"""
repository_service.py — Data-access and orchestration layer for repository entities.

Provides static methods that read/write the ``repositories``, ``files``,
``components``, ``relationships``, and ``content_chunks`` SQLite tables.

Key responsibilities:
  - ``create_repository``  : validate path / clone GitHub URL, INSERT the
    repository row, and immediately run a lightweight file discovery pass
    so the file tree is available before full analysis.
  - ``get_repository``     : fetch a single repository row and map it to
    a ``RepositoryResponse`` Pydantic model.
  - ``get_all_repositories``: list all repositories ordered by creation time.
  - ``get_tree``           : build a recursive ``TreeNodeDTO`` hierarchy from
    flat file rows, suitable for rendering a file-explorer sidebar.
  - ``get_file_detail``    : load file metadata, its extracted components, and
    a line-range excerpt from the raw source file on disk.
  - ``get_components``     : query all (or type-filtered) component rows.
  - ``get_relationships``  : query all (or type-filtered) relationship rows.
  - ``reset_repository``   : delete all analysis artefacts and reset counts
    so the repository can be re-analysed from scratch.
"""

import uuid
from datetime import datetime, timezone
import sqlite3
from typing import Optional, List, Dict, Any
from backend.app.models.domain import RepositoryStatus, RelationshipType, ComponentType
from backend.app.schemas.api import (
    RepositoryCreateRequest, RepositoryResponse, RepositoryCountsDTO,
    TreeNodeDTO, FileDetailResponse, ComponentDTO, ComponentListResponse,
    RelationshipDTO, RelationshipListResponse
)
from backend.app.storage.boundary import RepositoryBoundaryValidator, RepositoryBoundaryError
from backend.app.services.ingestion.ingestion_service import IngestionService
from backend.app.services.github_service import GithubService

class RepositoryService:

    @staticmethod
    def create_repository(conn: sqlite3.Connection, request: RepositoryCreateRequest) -> RepositoryResponse:
        """Register a new repository and perform an initial file discovery pass.

        For GitHub source types the URL is first passed to ``GithubService.clone_or_fetch``
        which performs a shallow ``git clone`` (or ZIP archive download as fallback)
        into ``data/clones/<owner>__<repo>/``.

        The resolved local path is then validated by ``RepositoryBoundaryValidator``
        to ensure it is a real directory and does not escape allowed roots.

        After the database row is inserted, ``IngestionService.ingest_repository``
        walks the directory tree and stores file records so the explorer sidebar
        is immediately populated without waiting for full analysis.

        Args:
            conn:    Active SQLite connection (obtained via ``get_db`` dependency).
            request: Validated ``RepositoryCreateRequest`` from the HTTP body.

        Returns:
            ``RepositoryResponse`` with the new repository ID, metadata, and
            discovery counts (``filesDiscovered``, ``filesSkipped``).

        Raises:
            ``RepositoryBoundaryError``: if the path is invalid or outside roots.
        """
        target_path_str = request.sourcePath or ""

        if request.sourceType == "github" or request.githubUrl or target_path_str.startswith("http://") or target_path_str.startswith("https://") or target_path_str.startswith("git@"):
            github_url = request.githubUrl or target_path_str
            target_path_str = GithubService.clone_or_fetch(github_url)

        validated_path = RepositoryBoundaryValidator.validate_repository_root(target_path_str)

        repo_id = f"repo_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        root_label = request.name.strip() or "root"

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO repositories (
                id, name, source_type, source_path, root_label, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, request.name, request.sourceType, validated_path, root_label, RepositoryStatus.CREATED.value, now)
        )
        conn.commit()

        # Discover and persist file records immediately after registration.
        files_discovered, files_skipped, _warnings = IngestionService.ingest_repository(
            conn, repo_id, validated_path
        )

        return RepositoryResponse(
            id=repo_id,
            name=request.name,
            sourceType=request.sourceType,
            sourcePath=validated_path,
            rootLabel=root_label,
            status=RepositoryStatus.CREATED,
            createdAt=now,
            counts=RepositoryCountsDTO(
                filesDiscovered=files_discovered,
                filesSkipped=files_skipped,
            )
        )

    @staticmethod
    def get_repository(conn: sqlite3.Connection, repo_id: str) -> Optional[RepositoryResponse]:
        """Fetch a single repository row by its ID.

        Returns ``None`` if no row with the given ``repo_id`` exists;
        the caller is responsible for converting ``None`` to a 404 response.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return RepositoryResponse(
            id=row["id"],
            name=row["name"],
            sourceType=row["source_type"],
            sourcePath=row["source_path"],
            rootLabel=row["root_label"],
            status=RepositoryStatus(row["status"]),
            createdAt=row["created_at"],
            analyzedAt=row["analyzed_at"],
            counts=RepositoryCountsDTO(
                filesDiscovered=row["files_discovered"],
                filesAnalyzed=row["files_analyzed"],
                filesSkipped=row["files_skipped"],
                componentsFound=row["components_found"],
                relationshipsFound=row["relationships_found"]
            )
        )

    @staticmethod
    def get_all_repositories(conn: sqlite3.Connection) -> List[RepositoryResponse]:
        """Return all registered repositories ordered newest-first."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM repositories ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [
            RepositoryResponse(
                id=r["id"],
                name=r["name"],
                sourceType=r["source_type"],
                sourcePath=r["source_path"],
                rootLabel=r["root_label"],
                status=RepositoryStatus(r["status"]),
                createdAt=r["created_at"],
                analyzedAt=r["analyzed_at"],
                counts=RepositoryCountsDTO(
                    filesDiscovered=r["files_discovered"],
                    filesAnalyzed=r["files_analyzed"],
                    filesSkipped=r["files_skipped"],
                    componentsFound=r["components_found"],
                    relationshipsFound=r["relationships_found"]
                )
            )
            for r in rows
        ]

    @staticmethod
    def get_tree(conn: sqlite3.Connection, repo_id: str) -> List[TreeNodeDTO]:
        """Build a recursive file-tree from flat file rows in the database.

        Iterates over all file paths for the repository (sorted alphabetically)
        and assembles a hierarchy of ``TreeNodeDTO`` objects where intermediate
        directory segments become synthetic directory nodes.  The resulting list
        contains only top-level nodes; children are nested inside each directory
        node’s ``children`` list.

        Returns an empty list if the repository has no indexed files yet.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT id, path, language, size_bytes FROM files WHERE repository_id = ? ORDER BY path ASC", (repo_id,))
        files = cursor.fetchall()

        if not files:
            return []

        nodes_by_path: Dict[str, TreeNodeDTO] = {}
        root_nodes: List[TreeNodeDTO] = []

        for f in files:
            parts = f["path"].split("/")
            curr_path = ""
            parent_node: Optional[TreeNodeDTO] = None

            for i, part in enumerate(parts):
                is_file = (i == len(parts) - 1)
                curr_path = f"{curr_path}/{part}" if curr_path else part

                if curr_path in nodes_by_path:
                    node = nodes_by_path[curr_path]
                else:
                    node_id = f["id"] if is_file else f"dir_{abs(hash(curr_path))}"
                    if is_file:
                        node = TreeNodeDTO(
                            id=f["id"],
                            name=part,
                            path=curr_path,
                            isDir=False,
                            language=f["language"],
                            sizeBytes=f["size_bytes"]
                        )
                    else:
                        node = TreeNodeDTO(
                            id=node_id,
                            name=part,
                            path=curr_path,
                            isDir=True,
                            children=[]
                        )
                    nodes_by_path[curr_path] = node

                    if parent_node is not None:
                        if parent_node.children is None:
                            parent_node.children = []
                        parent_node.children.append(node)
                    else:
                        root_nodes.append(node)

                parent_node = node

        return root_nodes

    @staticmethod
    def get_file_detail(
        conn: sqlite3.Connection,
        repo_id: str,
        file_id: str,
        start_line: Optional[int] = 1,
        end_line: Optional[int] = None
    ) -> Optional[FileDetailResponse]:
        """Return full detail for a file including its components and a source excerpt.

        Reads the raw file from disk using the repository’s ``source_path`` and
        the file’s relative ``path``.  The excerpt window defaults to 200 lines
        starting at ``start_line`` unless ``end_line`` is provided.

        If the file cannot be read (permissions, deleted, binary), the excerpt
        is set to ``"// Unable to read file excerpt"`` rather than raising an error.

        Returns ``None`` when either the file row or repository row is missing.
        """
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM files WHERE id = ? AND repository_id = ?", (file_id, repo_id))
        file_row = cursor.fetchone()
        if not file_row:
            return None

        cursor.execute("SELECT source_path FROM repositories WHERE id = ?", (repo_id,))
        repo_row = cursor.fetchone()
        if not repo_row:
            return None

        cursor.execute("SELECT * FROM components WHERE file_id = ? AND repository_id = ?", (file_id, repo_id))
        comp_rows = cursor.fetchall()
        components = [
            ComponentDTO(
                id=c["id"],
                fileId=c["file_id"],
                name=c["name"],
                type=ComponentType(c["type"]),
                startLine=c["start_line"],
                endLine=c["end_line"],
                signature=c["signature"],
                summary=c["summary"],
                isExported=bool(c["is_exported"]) if c["is_exported"] is not None else False,
                parentName=c["parent_name"],
            )
            for c in comp_rows
        ]

        excerpt = None
        full_file_path = RepositoryBoundaryValidator.resolve_safe_path(repo_row["source_path"], file_row["path"])

        try:
            with open(full_file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                start_idx = max(0, (start_line or 1) - 1)
                end_idx = min(len(lines), end_line) if end_line else min(len(lines), start_idx + 200)
                excerpt = "".join(lines[start_idx:end_idx])
        except Exception:
            excerpt = "// Unable to read file excerpt"

        return FileDetailResponse(
            id=file_row["id"],
            repositoryId=file_row["repository_id"],
            path=file_row["path"],
            language=file_row["language"],
            extension=file_row["extension"],
            sizeBytes=file_row["size_bytes"],
            status=file_row["status"],
            components=components,
            excerpt=excerpt,
            startLine=start_line or 1,
            endLine=end_line
        )

    @staticmethod
    def get_components(conn: sqlite3.Connection, repo_id: str, comp_type: Optional[str] = None) -> ComponentListResponse:
        """Return all extracted code components for a repository.

        Args:
            comp_type: Optional ``ComponentType`` value string (e.g. ``"function"``)
                       to filter results.  Returns all types when ``None``.
        """
        cursor = conn.cursor()
        if comp_type:
            cursor.execute("SELECT * FROM components WHERE repository_id = ? AND type = ?", (repo_id, comp_type))
        else:
            cursor.execute("SELECT * FROM components WHERE repository_id = ?", (repo_id,))
        rows = cursor.fetchall()
        comps = [
            ComponentDTO(
                id=c["id"],
                fileId=c["file_id"],
                name=c["name"],
                type=ComponentType(c["type"]),
                startLine=c["start_line"],
                endLine=c["end_line"],
                signature=c["signature"],
                summary=c["summary"],
                isExported=bool(c["is_exported"]) if c["is_exported"] is not None else False,
                parentName=c["parent_name"],
            )
            for c in rows
        ]
        return ComponentListResponse(repositoryId=repo_id, components=comps)

    @staticmethod
    def get_relationships(conn: sqlite3.Connection, repo_id: str, rel_type: Optional[str] = None) -> RelationshipListResponse:
        """Return all dependency edges for a repository.

        Args:
            rel_type: Optional ``RelationshipType`` value string
                      (e.g. ``"IMPORTS"``) to filter results.
        """
        cursor = conn.cursor()
        if rel_type:
            cursor.execute("SELECT * FROM relationships WHERE repository_id = ? AND type = ?", (repo_id, rel_type))
        else:
            cursor.execute("SELECT * FROM relationships WHERE repository_id = ?", (repo_id,))
        rows = cursor.fetchall()
        rels = [
            RelationshipDTO(
                id=r["id"],
                repositoryId=r["repository_id"],
                sourceType=r["source_type"],
                sourceId=r["source_id"],
                targetType=r["target_type"],
                targetId=r["target_id"],
                type=RelationshipType(r["type"]),
                confidence=r["confidence"],
                sourceLine=r["source_line"],
                evidence=r["evidence"]
            )
            for r in rows
        ]
        return RelationshipListResponse(repositoryId=repo_id, relationships=rels)

    @staticmethod
    def reset_repository(conn: sqlite3.Connection, repo_id: str) -> bool:
        """Delete all analysis artefacts for a repository and reset its status to CREATED.

        Removes rows from ``files``, ``components``, ``content_chunks``,
        ``relationships``, and ``analysis_jobs`` tables, then resets all numeric
        counters on the repository row.  The repository record itself is kept so
        the same ID can be re-analysed.

        Returns:
            Always ``True`` on success (the caller raises HTTP 404 before calling
            this if the repository does not exist).
        """
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE repository_id = ?", (repo_id,))
        cursor.execute("DELETE FROM components WHERE repository_id = ?", (repo_id,))
        cursor.execute("DELETE FROM content_chunks WHERE repository_id = ?", (repo_id,))
        cursor.execute("DELETE FROM relationships WHERE repository_id = ?", (repo_id,))
        cursor.execute("DELETE FROM analysis_jobs WHERE repository_id = ?", (repo_id,))
        cursor.execute(
            """
            UPDATE repositories SET
                status = 'CREATED',
                analyzed_at = NULL,
                files_discovered = 0,
                files_analyzed = 0,
                files_skipped = 0,
                components_found = 0,
                relationships_found = 0
            WHERE id = ?
            """,
            (repo_id,)
        )
        conn.commit()
        return True
