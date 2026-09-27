"""
analysis_service.py — Orchestrates the four-stage code analysis pipeline.

The pipeline is the core intelligence layer of RepoScope:

  Stage 1 – DISCOVERY
    ``RepositoryDiscovery.discover_files`` walks the repository tree and
    collects all analysable files, skipping binaries, large files, and
    entries matched by the ignore-list.

  Stage 2 – PARSING_STRUCTURE
    For each file: read content → ``StructureExtractor.extract_components``
    identifies named symbols (functions, classes, endpoints, …) → chunk
    content into 30-line ``content_chunks`` rows for retrieval.
    Directory records (synthetic DIRECTORY components) are also inserted here.

  Stage 3 – EXTRACTING_RELATIONSHIPS
    ``RelationshipExtractor.extract_relationships`` inspects import statements
    and cross-file call sites to build directed IMPORTS / USES / EXPORTS edges.

  Stage 4 – COMPLETED
    Aggregate counts are written back to ``repositories`` and ``analysis_jobs``
    rows; status transitions to READY.

On any unhandled exception the job transitions to FAILED and the error
message is persisted to ``analysis_jobs.error_message``.

A ``ThreadPoolExecutor`` (max 4 workers) is available for async execution;
however the default API path runs the pipeline synchronously in the request
thread to keep the Vercel serverless runtime simple.
"""

import uuid
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from backend.app.models.domain import RepositoryStatus
from backend.app.schemas.api import AnalysisJobResponse
from backend.app.services.ingestion.discovery import RepositoryDiscovery
from backend.app.services.structure.extractor import StructureExtractor, extract_directory_records
from backend.app.services.relationships.extractor import RelationshipExtractor
from backend.app.storage.boundary import RepositoryBoundaryValidator
from backend.app.core.database import get_db_connection

executor = ThreadPoolExecutor(max_workers=4)

class AnalysisService:

    @staticmethod
    def trigger_analysis(conn: sqlite3.Connection, repo_id: str, force: bool = False, run_async: bool = False) -> Optional[AnalysisJobResponse]:
        """Create an analysis job and optionally run the pipeline.

        If the repository is already ANALYZING and ``force`` is False, the
        existing in-progress job is returned without creating a duplicate.

        Args:
            conn:      Active SQLite connection.
            repo_id:   Target repository ID.
            force:     When True, always create a new job even if one is running.
            run_async: When True, submit the pipeline to the thread pool and
                       return immediately; when False (default) the pipeline
                       runs synchronously before this method returns.

        Returns:
            ``AnalysisJobResponse`` for the new or existing job, or ``None``
            if the repository does not exist.
        """
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,))
        repo = cursor.fetchone()
        if not repo:
            return None

        if repo["status"] == RepositoryStatus.ANALYZING.value and not force:
            cursor.execute("SELECT id FROM analysis_jobs WHERE repository_id = ? AND status = ?", (repo_id, RepositoryStatus.ANALYZING.value))
            existing = cursor.fetchone()
            if existing:
                return AnalysisService.get_job_status(conn, existing["id"])

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        source_path = repo["source_path"]

        cursor.execute(
            """
            INSERT INTO analysis_jobs (
                id, repository_id, status, progress, stage, started_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, repo_id, RepositoryStatus.ANALYZING.value, 0.0, "DISCOVERY", now)
        )

        cursor.execute("UPDATE repositories SET status = ? WHERE id = ?", (RepositoryStatus.ANALYZING.value, repo_id))
        conn.commit()

        if run_async:
            executor.submit(AnalysisService._async_worker, repo_id, job_id, source_path)
        else:
            AnalysisService.run_analysis_pipeline(conn, repo_id, job_id, source_path)

        return AnalysisService.get_job_status(conn, job_id)

    @staticmethod
    def _async_worker(repo_id: str, job_id: str, root_path: str):
        """Thread-pool worker that opens its own DB connection and runs the pipeline.

        A fresh connection is required because SQLite connections are not
        thread-safe.  The connection is always closed in the ``finally`` block.
        """
        conn = get_db_connection()
        try:
            AnalysisService.run_analysis_pipeline(conn, repo_id, job_id, root_path)
        finally:
            conn.close()

    @staticmethod
    def get_job_status(conn: sqlite3.Connection, job_id: str) -> Optional[AnalysisJobResponse]:
        """Fetch the current state of a single analysis job by its ID.

        Returns ``None`` if no job row exists with the given ``job_id``.
        The ``warnings`` JSON column is decoded to a Python list before returning.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None

        warnings = json.loads(row["warnings"]) if row["warnings"] else []

        return AnalysisJobResponse(
            id=row["id"],
            repositoryId=row["repository_id"],
            status=RepositoryStatus(row["status"]),
            progress=row["progress"],
            stage=row["stage"],
            filesDiscovered=row["files_discovered"],
            filesAnalyzed=row["files_analyzed"],
            filesSkipped=row["files_skipped"],
            componentsFound=row["components_found"],
            relationshipsFound=row["relationships_found"],
            warnings=warnings,
            error=row["error_message"],
            startedAt=row["started_at"],
            completedAt=row["completed_at"]
        )

    @staticmethod
    def run_analysis_pipeline(conn: sqlite3.Connection, repo_id: str, job_id: str, root_path: str):
        """Execute the full four-stage analysis pipeline within a single DB connection.

        This method is the primary entry point for both the synchronous and async
        execution paths.  It mutates the ``analysis_jobs`` and ``repositories`` rows
        throughout execution to reflect real-time progress.

        Data written per stage:
          - Stage 1: ``files_discovered``, ``files_skipped``, initial ``warnings``.
          - Stage 2: ``files`` rows, ``components`` rows, ``content_chunks`` rows.
          - Stage 3: ``relationships`` rows.
          - Stage 4: Final counts, ``status=READY``, ``completed_at`` timestamp.

        On exception: job status → FAILED, ``error_message`` is persisted.
        """
        cursor = conn.cursor()

        try:
            # Purge any data left from a previous analysis run before re-inserting.
            # This makes re-analysis a clean rebuild rather than an additive append,
            # preventing duplicate rows (files/components/chunks) and PRIMARY KEY
            # conflicts (relationships whose IDs are deterministic and therefore
            # identical across runs).
            # NOTE: analysis_jobs rows are NOT deleted here — the current job row
            # was just committed by trigger_analysis() and must be preserved.
            cursor.execute("DELETE FROM relationships  WHERE repository_id = ?", (repo_id,))
            cursor.execute("DELETE FROM content_chunks WHERE repository_id = ?", (repo_id,))
            cursor.execute("DELETE FROM components     WHERE repository_id = ?", (repo_id,))
            cursor.execute("DELETE FROM files          WHERE repository_id = ?", (repo_id,))
            conn.commit()

            # Stage 1: Discovery
            files, warnings = RepositoryDiscovery.discover_files(root_path)

            cursor.execute(
                """
                UPDATE analysis_jobs SET
                    stage = 'PARSING_STRUCTURE',
                    progress = 0.25,
                    files_discovered = ?,
                    files_skipped = ?,
                    warnings = ?
                WHERE id = ?
                """,
                (len(files), len(warnings), json.dumps(warnings), job_id)
            )
            conn.commit()

            # Stage 2: Structure Extraction & Chunking
            files_map = {}
            components_by_file = {}
            file_contents = {}
            total_components = 0

            for f_info in files:
                file_id = f"file_{uuid.uuid4().hex[:12]}"
                rel_path = f_info["relative_path"]
                full_path = f_info["full_path"]

                content = ""
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                except Exception as e:
                    warnings.append(f"Failed reading content for {rel_path}: {str(e)}")

                file_contents[file_id] = content
                files_map[file_id] = {
                    "id": file_id,
                    "repository_id": repo_id,
                    "path": rel_path,
                    "language": f_info["extension"].lstrip('.'),
                    "extension": f_info["extension"],
                    "size_bytes": f_info["size_bytes"],
                    "status": "READY"
                }

                cursor.execute(
                    """
                    INSERT INTO files (id, repository_id, path, language, extension, size_bytes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (file_id, repo_id, rel_path, f_info["extension"].lstrip('.'), f_info["extension"], f_info["size_bytes"], "READY")
                )

                comps = StructureExtractor.extract_components(file_id, repo_id, rel_path, content)
                components_by_file[file_id] = comps
                total_components += len(comps)

                for c in comps:
                    cursor.execute(
                        """
                        INSERT INTO components (id, file_id, repository_id, name, type, start_line, end_line, signature, summary, is_exported, parent_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            c["id"], c["file_id"], c["repository_id"], c["name"],
                            c["type"].value if hasattr(c["type"], "value") else c["type"],
                            c["start_line"], c["end_line"], c["signature"], c["summary"],
                            1 if c.get("is_exported") else 0,
                            c.get("parent_name"),
                        )
                    )

                lines = content.splitlines()
                chunk_size = 30
                for start_i in range(0, max(1, len(lines)), chunk_size):
                    chunk_lines = lines[start_i:start_i + chunk_size]
                    chunk_text = "\n".join(chunk_lines)
                    chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
                    token_estimate = len(chunk_text.split())
                    cursor.execute(
                        """
                        INSERT INTO content_chunks (id, repository_id, file_id, start_line, end_line, text, token_estimate)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (chunk_id, repo_id, file_id, start_i + 1, min(len(lines), start_i + chunk_size), chunk_text, token_estimate)
                    )

            # Extract and persist directory records (one per unique dir in the file set)
            dir_records = extract_directory_records(repo_id, [m["path"] for m in files_map.values()])
            for d in dir_records:
                cursor.execute(
                    """
                    INSERT INTO components (id, file_id, repository_id, name, type, start_line, end_line, signature, summary, is_exported, parent_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        d["id"], d["file_id"], d["repository_id"], d["name"],
                        d["type"].value if hasattr(d["type"], "value") else d["type"],
                        d["start_line"], d["end_line"], d["signature"], d["summary"],
                        0, d.get("parent_name"),
                    )
                )
            total_components += len(dir_records)

            cursor.execute(
                """
                UPDATE analysis_jobs SET
                    stage = 'EXTRACTING_RELATIONSHIPS',
                    progress = 0.65,
                    files_analyzed = ?,
                    components_found = ?
                WHERE id = ?
                """,
                (len(files_map), total_components, job_id)
            )
            conn.commit()

            # Stage 3: Relationship Extraction
            relationships = RelationshipExtractor.extract_relationships(repo_id, files_map, components_by_file, file_contents)

            for rel in relationships:
                cursor.execute(
                    """
                    INSERT INTO relationships (id, repository_id, source_type, source_id, target_type, target_id, type, confidence, source_line, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (rel["id"], rel["repository_id"], rel["source_type"], rel["source_id"], rel["target_type"], rel["target_id"], rel["type"].value if hasattr(rel["type"], "value") else rel["type"], rel["confidence"], rel["source_line"], rel["evidence"])
                )

            # Stage 4: Finalize Job & Update Repo
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE analysis_jobs SET
                    status = ?,
                    stage = 'COMPLETED',
                    progress = 1.0,
                    relationships_found = ?,
                    warnings = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (RepositoryStatus.READY.value, len(relationships), json.dumps(warnings), now, job_id)
            )

            cursor.execute(
                """
                UPDATE repositories SET
                    status = ?,
                    analyzed_at = ?,
                    files_discovered = ?,
                    files_analyzed = ?,
                    files_skipped = ?,
                    components_found = ?,
                    relationships_found = ?
                WHERE id = ?
                """,
                (
                    RepositoryStatus.READY.value,
                    now,
                    len(files),
                    len(files_map),
                    len(warnings),
                    total_components,
                    len(relationships),
                    repo_id
                )
            )
            conn.commit()

        except Exception as e:
            cursor.execute(
                """
                UPDATE analysis_jobs SET
                    status = ?,
                    stage = 'FAILED',
                    error_message = ?
                WHERE id = ?
                """,
                (RepositoryStatus.FAILED.value, str(e), job_id)
            )
            cursor.execute("UPDATE repositories SET status = ? WHERE id = ?", (RepositoryStatus.FAILED.value, repo_id))
            conn.commit()
