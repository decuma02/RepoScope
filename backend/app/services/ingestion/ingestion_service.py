"""
Repository Ingestion Service
============================
Discovers all source files within a validated repository root, then
persists a FileEntity record for each one.  This is the *only* component
that writes to the `files` table during the initial ingestion step.

What it does
------------
* Re-validates the root path (boundary + symlink safety).
* Walks the directory tree, pruning ignored directories.
* Skips files that match ignore rules (binary, generated, secrets, too large).
* Does NOT follow symlinks that escape the repository boundary.
* Normalises relative paths to forward-slash format.
* Detects a canonical language name from the file extension.
* Computes a SHA-256 content hash for each accepted file.
* Inserts one `files` row per accepted file inside a single transaction.
* Updates the repository counters (files_discovered, files_skipped) atomically.

What it does NOT do
-------------------
* AI, embeddings, vector DB, graph construction, relationship extraction.
* Component / chunk parsing (that is the Analysis pipeline's job).
* Multi-repository support.
"""

import hashlib
import os
import sqlite3
import uuid
from typing import List, Tuple, Dict, Any

from backend.app.core.config import settings
from backend.app.services.ingestion.discovery import RepositoryDiscovery
from backend.app.storage.boundary import RepositoryBoundaryValidator, RepositoryBoundaryError


def _language_for_extension(ext: str) -> str:
    """Return the canonical language name for a file extension, or the bare extension."""
    return settings.EXTENSION_LANGUAGE_MAP.get(ext.lower(), ext.lstrip("."))


def _sha256_of_file(full_path: str) -> str:
    """Return the hex SHA-256 digest of a file's content."""
    h = hashlib.sha256()
    try:
        with open(full_path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
    except OSError:
        return ""
    return h.hexdigest()


class IngestionService:
    """
    Ingests a single repository: discovers source files and writes
    one `files` row per discovered file inside a single DB transaction.
    """

    @staticmethod
    def ingest_repository(
        conn: sqlite3.Connection,
        repo_id: str,
        source_path: str,
    ) -> Tuple[int, int, List[str]]:
        """
        Discover and persist all source files for *repo_id*.

        Parameters
        ----------
        conn        : open SQLite connection with row_factory set.
        repo_id     : the repository record that already exists in the DB.
        source_path : the validated absolute path stored in the repository row.

        Returns
        -------
        (files_discovered, files_skipped, warnings)
        """
        # Re-validate the root (guards against DB row pointing to a deleted path).
        validated_root = RepositoryBoundaryValidator.validate_repository_root(source_path)

        discovered_files, warnings = RepositoryDiscovery.discover_files(validated_root)

        files_skipped = len(warnings)
        file_rows: List[Dict[str, Any]] = []

        for f_info in discovered_files:
            full_path: str = f_info["full_path"]
            rel_path: str = f_info["relative_path"]   # already forward-slash
            ext: str = f_info["extension"]
            size_bytes: int = f_info["size_bytes"]

            language = _language_for_extension(ext)
            content_hash = _sha256_of_file(full_path)
            file_id = f"file_{uuid.uuid4().hex[:12]}"

            file_rows.append({
                "id": file_id,
                "repository_id": repo_id,
                "path": rel_path,
                "language": language,
                "extension": ext,
                "size_bytes": size_bytes,
                "content_hash": content_hash,
                "status": "READY",
            })

        cursor = conn.cursor()

        # Persist all file records in a single transaction.
        cursor.executemany(
            """
            INSERT INTO files (id, repository_id, path, language, extension,
                               size_bytes, content_hash, status)
            VALUES (:id, :repository_id, :path, :language, :extension,
                    :size_bytes, :content_hash, :status)
            """,
            file_rows,
        )

        # Update repository-level counters.
        cursor.execute(
            """
            UPDATE repositories
               SET files_discovered = ?,
                   files_skipped    = ?
             WHERE id = ?
            """,
            (len(discovered_files), files_skipped, repo_id),
        )

        conn.commit()

        return len(discovered_files), files_skipped, warnings
