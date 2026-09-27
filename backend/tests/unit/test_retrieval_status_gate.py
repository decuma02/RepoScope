"""
Unit tests for the retrieval status gate added to the search API.

Tests cover three cases:
  a. READY repository       → search proceeds (HTTP 200)
  b. ANALYZING repository   → retrieval is blocked (HTTP 409, code REPOSITORY_ANALYZING)
  c. Missing repository     → HTTP 404 (code REPOSITORY_NOT_FOUND)
  d. CREATED repository     → retrieval is blocked (HTTP 409, code REPOSITORY_NOT_READY)
  e. FAILED repository      → retrieval is blocked (HTTP 409, code REPOSITORY_NOT_READY)

The tests use an in-memory SQLite database so they never touch the on-disk store
and do not depend on Member 1's ingestion or analysis services.
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_in_memory_db() -> sqlite3.Connection:
    """Create a minimal in-memory schema matching the real DB structure."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE repositories (
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
        )
    """)
    conn.execute("""
        CREATE TABLE files (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            path TEXT NOT NULL,
            language TEXT,
            extension TEXT,
            size_bytes INTEGER DEFAULT 0,
            content_hash TEXT,
            status TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE components (
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
        )
    """)
    conn.execute("""
        CREATE TABLE relationships (
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
        )
    """)
    conn.commit()
    return conn


def _insert_repo(conn: sqlite3.Connection, repo_id: str, status: str, source_path: str = "/tmp") -> None:
    conn.execute(
        """
        INSERT INTO repositories
            (id, name, source_type, source_path, root_label, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (repo_id, "Test Repo", "local_path", source_path, "root", status, "2024-01-01T00:00:00+00:00"),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    conn = _make_in_memory_db()
    yield conn
    conn.close()


@pytest.fixture()
def client(db):
    """FastAPI test client with the in-memory DB injected via dependency override."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: /search endpoint
# ---------------------------------------------------------------------------

class TestSearchStatusGate:
    def test_missing_repository_returns_404(self, client):
        """A repo ID that does not exist must return HTTP 404."""
        res = client.post(
            "/api/repositories/repo_nonexistent/search",
            json={"query": "boundary", "limit": 5, "relationshipAware": False},
        )
        assert res.status_code == 404
        error = res.json()["error"]
        assert error["code"] == "REPOSITORY_NOT_FOUND"

    def test_analyzing_repository_returns_409(self, client, db):
        """A repo in ANALYZING status must block retrieval with HTTP 409."""
        _insert_repo(db, "repo_analyzing", "ANALYZING")
        res = client.post(
            "/api/repositories/repo_analyzing/search",
            json={"query": "boundary", "limit": 5, "relationshipAware": False},
        )
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "REPOSITORY_ANALYZING"
        assert "try again shortly" in error["message"].lower()

    def test_created_repository_returns_409(self, client, db):
        """A repo in CREATED status (never analyzed) must block retrieval with HTTP 409."""
        _insert_repo(db, "repo_created", "CREATED")
        res = client.post(
            "/api/repositories/repo_created/search",
            json={"query": "boundary", "limit": 5, "relationshipAware": False},
        )
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "REPOSITORY_NOT_READY"

    def test_failed_repository_returns_409(self, client, db):
        """A repo in FAILED status must block retrieval with HTTP 409."""
        _insert_repo(db, "repo_failed", "FAILED")
        res = client.post(
            "/api/repositories/repo_failed/search",
            json={"query": "boundary", "limit": 5, "relationshipAware": False},
        )
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "REPOSITORY_NOT_READY"

    def test_ready_repository_proceeds(self, client, db):
        """A READY repository must reach the retrieval engine and return HTTP 200."""
        _insert_repo(db, "repo_ready", "READY")
        res = client.post(
            "/api/repositories/repo_ready/search",
            json={"query": "boundary", "limit": 5, "relationshipAware": False},
        )
        # Retrieval engine runs; no files exist → empty results, but HTTP 200
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert isinstance(data["results"], list)


# ---------------------------------------------------------------------------
# Tests: /compare-retrieval endpoint (same gate, same expected behaviour)
# ---------------------------------------------------------------------------

class TestCompareRetrievalStatusGate:
    def test_missing_repository_returns_404(self, client):
        res = client.post(
            "/api/repositories/repo_nonexistent/compare-retrieval",
            json={"query": "boundary"},
        )
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "REPOSITORY_NOT_FOUND"

    def test_analyzing_repository_returns_409(self, client, db):
        _insert_repo(db, "repo_analyzing2", "ANALYZING")
        res = client.post(
            "/api/repositories/repo_analyzing2/compare-retrieval",
            json={"query": "boundary"},
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "REPOSITORY_ANALYZING"

    def test_ready_repository_proceeds(self, client, db):
        _insert_repo(db, "repo_ready2", "READY")
        res = client.post(
            "/api/repositories/repo_ready2/compare-retrieval",
            json={"query": "boundary"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "relationshipAwareResults" in data
        assert "textOnlyBaselineResults" in data
