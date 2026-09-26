import uuid
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from app.models.domain import RepositoryStatus
from app.models.api import AnalysisJobResponse
from app.analysis.discovery import RepositoryDiscovery
from app.analysis.structure import StructureExtractor
from app.analysis.relationships import RelationshipExtractor
from app.security.repository_boundary import RepositoryBoundaryValidator

class AnalysisService:

    @staticmethod
    def trigger_analysis(conn: sqlite3.Connection, repo_id: str, force: bool = False) -> Optional[AnalysisJobResponse]:
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

        AnalysisService.run_analysis_pipeline(conn, repo_id, job_id, repo["source_path"])

        return AnalysisService.get_job_status(conn, job_id)

    @staticmethod
    def get_job_status(conn: sqlite3.Connection, job_id: str) -> Optional[AnalysisJobResponse]:
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
        cursor = conn.cursor()

        try:
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

                # Extract Components
                comps = StructureExtractor.extract_components(file_id, repo_id, rel_path, content)
                components_by_file[file_id] = comps
                total_components += len(comps)

                for c in comps:
                    cursor.execute(
                        """
                        INSERT INTO components (id, file_id, repository_id, name, type, start_line, end_line, signature, summary)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (c["id"], c["file_id"], c["repository_id"], c["name"], c["type"].value if hasattr(c["type"], "value") else c["type"], c["start_line"], c["end_line"], c["signature"], c["summary"])
                    )

                # Generate & Persist Content Chunks (~30 lines each)
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
