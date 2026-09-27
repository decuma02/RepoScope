"""
Regression tests for re-analysis / idempotency of the analysis pipeline.

Background
----------
Running analysis twice on the same repository used to:
  1. Silently double every files / components / content_chunks row (UUID IDs
     are always unique, so plain INSERT never raises an error).
  2. Raise IntegrityError on the first duplicate relationship (whose IDs ARE
     deterministic / SHA-1-based), leaving the repository stuck in FAILED.

Fix
---
run_analysis_pipeline() now deletes all derived data for the repository
(files, components, content_chunks, relationships) at the very start of every
run, before any inserts.  This makes re-analysis a clean rebuild and prevents
both the silent duplication and the PRIMARY KEY conflict.

Tests in this module
--------------------
1. Second run does not crash  → repo ends in READY, not FAILED / ANALYZING.
2. File count is identical after first and second run  → no doubling.
3. Component count is identical after both runs.
4. Relationship count is identical after both runs.
5. No duplicate relationship IDs in the DB after second run.
6. Analysis job history grows (a new job is recorded per run).
7. A failed first run does NOT permanently strand the repo in ANALYZING
   (the failure handler sets FAILED; a subsequent trigger_analysis call
   can still run and recover to READY).
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import pytest

from backend.app.models.domain import RepositoryStatus
from backend.app.services.analysis_service import AnalysisService


# ---------------------------------------------------------------------------
# Minimal full-schema in-memory DB (mirrors database.py without touching disk)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    root_label TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    analyzed_at TEXT,
    files_discovered INTEGER DEFAULT 0,
    files_analyzed INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    components_found INTEGER DEFAULT 0,
    relationships_found INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    path TEXT NOT NULL,
    language TEXT,
    extension TEXT,
    size_bytes INTEGER DEFAULT 0,
    content_hash TEXT,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS components (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT,
    summary TEXT,
    is_exported INTEGER NOT NULL DEFAULT 0,
    parent_name TEXT
);
CREATE TABLE IF NOT EXISTS content_chunks (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_estimate INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source_line INTEGER,
    evidence TEXT
);
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL DEFAULT 0.0,
    stage TEXT NOT NULL,
    files_discovered INTEGER DEFAULT 0,
    files_analyzed INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    components_found INTEGER DEFAULT 0,
    relationships_found INTEGER DEFAULT 0,
    warnings TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
"""


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Fixture: a tiny on-disk repo with Python + TS files that produce both
# imports and exports, so the relationship extractor has real work to do.
# ---------------------------------------------------------------------------

_PY_UTILS = """\
\"\"\"Utility helpers.\"\"\"

__all__ = ["helper"]


def helper(x):
    return x
"""

_PY_SERVICE = """\
\"\"\"Service layer.\"\"\"
from src.utils import helper


def create(name: str):
    return helper(name)
"""

_TS_UTILS = """\
export function formatDate(d: Date): string {
    return d.toISOString().slice(0, 10);
}
"""

_TSX_APP = """\
import React from 'react';
import { formatDate } from './utils';

export default function App() {
    return formatDate(new Date());
}
"""


@pytest.fixture()
def repo_dir(tmp_path: Path) -> Path:
    """Create a minimal source tree that the discovery + extractor can process."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.py").write_text(_PY_UTILS, encoding="utf-8")
    (src / "service.py").write_text(_PY_SERVICE, encoding="utf-8")

    fe = tmp_path / "frontend"
    fe.mkdir()
    (fe / "utils.ts").write_text(_TS_UTILS, encoding="utf-8")
    (fe / "app.tsx").write_text(_TSX_APP, encoding="utf-8")

    return tmp_path


def _seed_repo(conn: sqlite3.Connection, repo_dir: Path) -> str:
    """Insert a repository row and return its ID."""
    repo_id = f"repo_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO repositories (id, name, source_type, source_path, root_label, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (repo_id, "test-repo", "LOCAL", str(repo_dir), "root",
         RepositoryStatus.CREATED.value, now),
    )
    conn.commit()
    return repo_id


def _run_once(conn: sqlite3.Connection, repo_id: str) -> str:
    """
    Call trigger_analysis in synchronous mode and return the job_id.
    Resets the repo status to CREATED first so trigger_analysis does not
    skip the run (it guards against concurrent ANALYZING only, but we reset
    to CREATED to simulate a fresh trigger each time).
    """
    conn.execute("UPDATE repositories SET status = ? WHERE id = ?",
                 (RepositoryStatus.CREATED.value, repo_id))
    conn.commit()

    job = AnalysisService.trigger_analysis(conn, repo_id, force=False, run_async=False)
    assert job is not None
    return job.id


def _counts(conn: sqlite3.Connection, repo_id: str) -> Tuple[int, int, int, int]:
    """Return (files, components, chunks, relationships) row counts for repo_id."""
    def q(table):
        return conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
    return q("files"), q("components"), q("content_chunks"), q("relationships")


# ===========================================================================
# 1. Second run does not crash — repo ends in READY
# ===========================================================================

class TestSecondRunCompletes:
    def test_first_run_reaches_ready(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        row = conn.execute("SELECT status FROM repositories WHERE id = ?",
                           (repo_id,)).fetchone()
        assert row["status"] == RepositoryStatus.READY.value

    def test_second_run_reaches_ready(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        _run_once(conn, repo_id)  # must not raise or leave FAILED
        row = conn.execute("SELECT status FROM repositories WHERE id = ?",
                           (repo_id,)).fetchone()
        assert row["status"] == RepositoryStatus.READY.value, (
            f"Repo status after second run: {row['status']!r} (expected READY)"
        )

    def test_second_job_is_completed(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        job2_id = _run_once(conn, repo_id)
        row = conn.execute("SELECT status FROM analysis_jobs WHERE id = ?",
                           (job2_id,)).fetchone()
        assert row["status"] == RepositoryStatus.READY.value


# ===========================================================================
# 2. File count is identical after first and second run — no doubling
# ===========================================================================

class TestNoDuplicateFiles:
    def test_file_count_stable_after_second_run(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        files_after_first = conn.execute(
            "SELECT COUNT(*) FROM files WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]

        _run_once(conn, repo_id)
        files_after_second = conn.execute(
            "SELECT COUNT(*) FROM files WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]

        assert files_after_first == files_after_second, (
            f"File rows doubled: {files_after_first} → {files_after_second}"
        )

    def test_file_count_nonzero(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        count = conn.execute(
            "SELECT COUNT(*) FROM files WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
        assert count >= 4, f"Expected at least 4 files, got {count}"


# ===========================================================================
# 3. Component count identical after both runs
# ===========================================================================

class TestNoDuplicateComponents:
    def test_component_count_stable(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        c1 = conn.execute(
            "SELECT COUNT(*) FROM components WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
        _run_once(conn, repo_id)
        c2 = conn.execute(
            "SELECT COUNT(*) FROM components WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
        assert c1 == c2, f"Component rows doubled: {c1} → {c2}"


# ===========================================================================
# 4. Relationship count identical after both runs
# ===========================================================================

class TestNoDuplicateRelationships:
    def test_relationship_count_stable(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        r1 = conn.execute(
            "SELECT COUNT(*) FROM relationships WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
        _run_once(conn, repo_id)
        r2 = conn.execute(
            "SELECT COUNT(*) FROM relationships WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
        assert r1 == r2, f"Relationship rows doubled: {r1} → {r2}"


# ===========================================================================
# 5. No duplicate relationship IDs in the DB after second run
# ===========================================================================

class TestNoDuplicateRelationshipIds:
    def test_all_relationship_ids_unique(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        _run_once(conn, repo_id)
        _run_once(conn, repo_id)
        rows = conn.execute(
            "SELECT id FROM relationships WHERE repository_id = ?", (repo_id,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids)), "Duplicate relationship IDs found after second run"


# ===========================================================================
# 6. Analysis job history grows — a new job per run
# ===========================================================================

class TestJobHistoryGrows:
    def test_two_runs_create_two_jobs(self, repo_dir):
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)
        job1_id = _run_once(conn, repo_id)
        job2_id = _run_once(conn, repo_id)
        assert job1_id != job2_id, "Expected distinct job IDs for each run"
        count = conn.execute(
            "SELECT COUNT(*) FROM analysis_jobs WHERE repository_id = ?", (repo_id,)
        ).fetchone()[0]
        assert count == 2


# ===========================================================================
# 7. Failed first run does NOT permanently leave repo in ANALYZING
# ===========================================================================

class TestFailedRunRecovery:
    def test_failed_run_leaves_repo_in_failed_not_analyzing(self, tmp_path):
        """
        If the analysis fails (e.g. root path deleted mid-run), the repo must
        end up in FAILED, not stuck in ANALYZING.
        """
        conn = _make_db()
        # Point to a path that does not exist → discovery will fail immediately
        repo_id = f"repo_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO repositories (id, name, source_type, source_path, root_label, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (repo_id, "broken-repo", "LOCAL", str(tmp_path / "nonexistent"),
             "root", RepositoryStatus.CREATED.value, now),
        )
        conn.commit()

        job = AnalysisService.trigger_analysis(conn, repo_id, force=False, run_async=False)
        assert job is not None

        row = conn.execute("SELECT status FROM repositories WHERE id = ?",
                           (repo_id,)).fetchone()
        assert row["status"] == RepositoryStatus.FAILED.value, (
            f"Expected FAILED after error, got {row['status']!r}"
        )
        # Must NOT be stuck in ANALYZING
        assert row["status"] != RepositoryStatus.ANALYZING.value

    def test_second_run_after_failed_first_run_recovers(self, repo_dir):
        """
        A repo left in FAILED state can be re-analysed and recover to READY.
        """
        conn = _make_db()
        repo_id = _seed_repo(conn, repo_dir)

        # Manually put the repo in FAILED (simulates a previous failed run)
        conn.execute("UPDATE repositories SET status = ? WHERE id = ?",
                     (RepositoryStatus.FAILED.value, repo_id))
        conn.commit()

        # trigger_analysis should start a new run regardless of FAILED status
        job = AnalysisService.trigger_analysis(conn, repo_id, force=False, run_async=False)
        assert job is not None

        row = conn.execute("SELECT status FROM repositories WHERE id = ?",
                           (repo_id,)).fetchone()
        assert row["status"] == RepositoryStatus.READY.value, (
            f"Expected READY after recovery run, got {row['status']!r}"
        )
