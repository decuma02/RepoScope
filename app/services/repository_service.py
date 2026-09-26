import uuid
from datetime import datetime, timezone
import sqlite3
from typing import Optional, List, Dict, Any
from app.models.domain import RepositoryStatus
from app.models.api import RepositoryCreateRequest, RepositoryResponse, RepositoryCountsDTO, TreeNodeDTO, FileDetailResponse, ComponentDTO
from app.security.repository_boundary import RepositoryBoundaryValidator, RepositoryBoundaryError

class RepositoryService:

    @staticmethod
    def create_repository(conn: sqlite3.Connection, request: RepositoryCreateRequest) -> RepositoryResponse:
        validated_path = RepositoryBoundaryValidator.validate_repository_root(request.sourcePath)

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

        return RepositoryResponse(
            id=repo_id,
            name=request.name,
            sourceType=request.sourceType,
            sourcePath=validated_path,
            rootLabel=root_label,
            status=RepositoryStatus.CREATED,
            createdAt=now,
            counts=RepositoryCountsDTO()
        )

    @staticmethod
    def get_repository(conn: sqlite3.Connection, repo_id: str) -> Optional[RepositoryResponse]:
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
        cursor = conn.cursor()
        cursor.execute("SELECT id, path, language, size_bytes FROM files WHERE repository_id = ? ORDER BY path ASC", (repo_id,))
        files = cursor.fetchall()

        if not files:
            return []

        root_nodes: Dict[str, TreeNodeDTO] = {}

        for f in files:
            parts = f["path"].split("/")
            curr_path = ""
            for i, part in enumerate(parts):
                is_file = (i == len(parts) - 1)
                curr_path = f"{curr_path}/{part}" if curr_path else part
                node_id = f["id"] if is_file else f"dir_{hash(curr_path)}"

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

                if i == 0:
                    if curr_path not in root_nodes:
                        root_nodes[curr_path] = node
                # Note: A full recursive hierarchy map can be attached if children exist

        return list(root_nodes.values())

    @staticmethod
    def get_file_detail(
        conn: sqlite3.Connection,
        repo_id: str,
        file_id: str,
        start_line: Optional[int] = 1,
        end_line: Optional[int] = None
    ) -> Optional[FileDetailResponse]:
        cursor = conn.cursor()

        # Fetch file record
        cursor.execute("SELECT * FROM files WHERE id = ? AND repository_id = ?", (file_id, repo_id))
        file_row = cursor.fetchone()
        if not file_row:
            return None

        # Fetch repo record for root path
        cursor.execute("SELECT source_path FROM repositories WHERE id = ?", (repo_id,))
        repo_row = cursor.fetchone()
        if not repo_row:
            return None

        # Fetch components
        cursor.execute(
            "SELECT * FROM components WHERE file_id = ? AND repository_id = ?", (file_id, repo_id)
        )
        comp_rows = cursor.fetchall()
        components = [
            ComponentDTO(
                id=c["id"],
                fileId=c["file_id"],
                name=c["name"],
                type=c["type"],
                startLine=c["start_line"],
                endLine=c["end_line"],
                signature=c["signature"],
                summary=c["summary"]
            )
            for c in comp_rows
        ]

        # Read excerpt safely
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
