"""
Focused unit tests for content-chunk matching in RetrievalService.search().

Covers:
  1.  Query term found only in chunk text → file is returned.
  2.  Chunk match contributes to lexical score.
  3.  startLine comes from matching chunk.
  4.  endLine comes from matching chunk.
  5.  excerpt equals matching chunk text.
  6.  No chunk match → existing path/component behaviour remains.
  7.  Multi-term query → chunk containing more query terms ranks higher.
  8.  Chunk-seeded file still triggers 1-hop relationship expansion.
  9.  Relationship-only file still uses existing first-25-lines fallback.
  10. Chunks from another repository are ignored.

All tests use an in-memory SQLite database and do NOT touch the on-disk store.
"""
import sqlite3
import pytest
from backend.app.services.retrieval.search_engine import RetrievalService
from backend.app.schemas.api import SearchRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> sqlite3.Connection:
    """Minimal in-memory DB with the full schema used by RetrievalService."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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
        );
        CREATE TABLE files (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            path TEXT NOT NULL,
            language TEXT,
            extension TEXT,
            size_bytes INTEGER DEFAULT 0,
            content_hash TEXT,
            status TEXT NOT NULL
        );
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
        );
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
        );
        CREATE TABLE content_chunks (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            file_id TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            text TEXT NOT NULL,
            token_estimate INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn


def _insert_repo(conn, repo_id="repo1", source_path="/tmp/repo"):
    conn.execute(
        "INSERT INTO repositories (id, name, source_type, source_path, root_label, status, created_at) "
        "VALUES (?, 'Repo', 'local_path', ?, 'root', 'READY', '2024-01-01T00:00:00+00:00')",
        (repo_id, source_path),
    )
    conn.commit()


def _insert_file(conn, file_id, repo_id="repo1", path="src/foo.py"):
    conn.execute(
        "INSERT INTO files (id, repository_id, path, status) VALUES (?, ?, ?, 'analyzed')",
        (file_id, repo_id, path),
    )
    conn.commit()


def _insert_chunk(conn, chunk_id, repo_id, file_id, start_line, end_line, text):
    conn.execute(
        "INSERT INTO content_chunks (id, repository_id, file_id, start_line, end_line, text) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id, repo_id, file_id, start_line, end_line, text),
    )
    conn.commit()


def _insert_relationship(conn, rel_id, repo_id, src_id, tgt_id,
                         src_type="file", tgt_type="file", rel_type="IMPORTS"):
    conn.execute(
        "INSERT INTO relationships "
        "(id, repository_id, source_type, source_id, target_type, target_id, type, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1.0)",
        (rel_id, repo_id, src_type, src_id, tgt_type, tgt_id, rel_type),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Test 1: Query term found only in chunk text → file is returned
# ---------------------------------------------------------------------------

def test_chunk_only_match_returns_file():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/unrelated_path.py")
    _insert_chunk(conn, "c1", "repo1", "f1", 10, 39, "def authenticate_user(token): pass")

    req = SearchRequest(query="authenticate", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    file_ids = [r.fileId for r in resp.results]
    assert "f1" in file_ids, "File matched only via chunk text must appear in results"


# ---------------------------------------------------------------------------
# Test 2: Chunk match contributes to lexical score
# ---------------------------------------------------------------------------

def test_chunk_match_contributes_to_lexical_score():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/unrelated.py")
    _insert_chunk(conn, "c1", "repo1", "f1", 1, 30, "def process_payment(): pass")

    req = SearchRequest(query="process", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f1")
    # Content score: 1 term matched → +1.0; lexicalScore should be >= 1.0 (capped at 1.0)
    assert result.lexicalScore >= 1.0


# ---------------------------------------------------------------------------
# Test 3: startLine comes from matching chunk
# ---------------------------------------------------------------------------

def test_start_line_from_chunk():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/unrelated.py")
    _insert_chunk(conn, "c1", "repo1", "f1", 61, 90, "def validate_token(): pass")

    req = SearchRequest(query="validate", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f1")
    assert result.startLine == 61


# ---------------------------------------------------------------------------
# Test 4: endLine comes from matching chunk
# ---------------------------------------------------------------------------

def test_end_line_from_chunk():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/unrelated.py")
    _insert_chunk(conn, "c1", "repo1", "f1", 61, 90, "def validate_token(): pass")

    req = SearchRequest(query="validate", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f1")
    assert result.endLine == 90


# ---------------------------------------------------------------------------
# Test 5: excerpt equals matching chunk text
# ---------------------------------------------------------------------------

def test_excerpt_equals_chunk_text():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/unrelated.py")
    chunk_text = "def parse_request(data):\n    return json.loads(data)\n"
    _insert_chunk(conn, "c1", "repo1", "f1", 31, 60, chunk_text)

    req = SearchRequest(query="parse", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f1")
    assert result.excerpt == chunk_text


# ---------------------------------------------------------------------------
# Test 6: No chunk match → existing path/component behaviour remains
# ---------------------------------------------------------------------------

def test_no_chunk_match_path_component_still_works():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_path", path="src/authentication_service.py")
    _insert_chunk(conn, "c_other", "repo1", "f_path", 1, 30, "def unrelated(): pass")

    req = SearchRequest(query="authentication", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    file_ids = [r.fileId for r in resp.results]
    assert "f_path" in file_ids, "Path-matched file must still appear even if chunk doesn't match"


# ---------------------------------------------------------------------------
# Test 7: Multi-term query → chunk with more terms ranks higher
# ---------------------------------------------------------------------------

def test_multi_term_more_matching_chunk_ranks_higher():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/a.py")
    _insert_file(conn, "f2", path="src/b.py")
    # f1 chunk matches only 1 term
    _insert_chunk(conn, "c1", "repo1", "f1", 1, 30, "def authorize(): pass")
    # f2 chunk matches both terms
    _insert_chunk(conn, "c2", "repo1", "f2", 1, 30, "def authorize_user(user): pass")

    req = SearchRequest(query="authorize user", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    ids_in_order = [r.fileId for r in resp.results]
    assert ids_in_order.index("f2") < ids_in_order.index("f1"), \
        "f2 (2 matching terms) should rank above f1 (1 matching term)"


# ---------------------------------------------------------------------------
# Test 8: Chunk-seeded file triggers 1-hop relationship expansion
# ---------------------------------------------------------------------------

def test_chunk_seeded_file_triggers_relationship_expansion():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed", path="src/seed.py")
    _insert_file(conn, "f_related", path="src/related.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def compute_hash(data): pass")
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_related")

    req = SearchRequest(query="compute", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    file_ids = [r.fileId for r in resp.results]
    assert "f_related" in file_ids, \
        "f_related must be discovered via 1-hop expansion from chunk-seeded f_seed"


# ---------------------------------------------------------------------------
# Test 9: Relationship-only file still uses first-25-lines fallback (no chunk)
# ---------------------------------------------------------------------------

def test_relationship_only_file_uses_fallback_startline():
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed", path="src/seed.py")
    _insert_file(conn, "f_related", path="src/related.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def compute_hash(data): pass")
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_related")

    req = SearchRequest(query="compute", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    related_result = next(r for r in resp.results if r.fileId == "f_related")
    # No chunk for f_related → fallback startLine must be 1
    assert related_result.startLine == 1
    # Fallback endLine must be min(25, 200) = 25
    assert related_result.endLine == 25


# ---------------------------------------------------------------------------
# Test 10: Chunks from another repository are ignored
# ---------------------------------------------------------------------------

def test_chunks_from_other_repo_are_ignored():
    conn = _make_db()
    _insert_repo(conn, "repo1")
    _insert_repo(conn, "repo2", source_path="/tmp/repo2")
    _insert_file(conn, "f_other", "repo2", path="src/other.py")
    # Only chunk belongs to repo2, not repo1
    _insert_chunk(conn, "c_other", "repo2", "f_other", 1, 30, "def fetch_records(): pass")

    req = SearchRequest(query="fetch", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    file_ids = [r.fileId for r in resp.results]
    assert "f_other" not in file_ids, \
        "Files from repo2 must not appear in repo1 search results"
