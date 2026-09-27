"""
Focused unit tests for confidence-weighted 1-hop relationship scoring.

Covers:
  1.  IMPORTS confidence 0.95 → relationship bonus 0.38.
  2.  USES confidence 0.75 → relationship bonus 0.30.
  3.  Expansion works when seed is the relationship source.
  4.  Expansion works when seed is the relationship target.
  5.  Multiple relationships to the same file preserve additive file scoring.
  6.  Reported relationshipBonus matches the actual weighted bonus.
  7.  Direct lexical matches still work unchanged (path / component matching).
  8.  relationshipAware=False gives relationshipBonus == 0.
  9.  Existing content-chunk retrieval behaviour is unaffected.
  10. Existing retrieval status-gate behaviour is unaffected (no HTTP changes).

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
                         src_type="file", tgt_type="file",
                         rel_type="IMPORTS", confidence=1.0):
    conn.execute(
        "INSERT INTO relationships "
        "(id, repository_id, source_type, source_id, target_type, target_id, type, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rel_id, repo_id, src_type, src_id, tgt_type, tgt_id, rel_type, confidence),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Test 1: IMPORTS confidence 0.95 → relationship bonus 0.38
# ---------------------------------------------------------------------------

def test_imports_confidence_095_gives_bonus_038():
    """
    An IMPORTS relationship with confidence=0.95 must produce
    relationshipBonus == round(0.95 * 0.4, 2) == 0.38 on the expanded file.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed", path="src/seed.py")
    _insert_file(conn, "f_expanded", path="src/expanded.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def compute(): pass")
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_expanded",
                         rel_type="IMPORTS", confidence=0.95)

    req = SearchRequest(query="compute", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    expanded = next(r for r in resp.results if r.fileId == "f_expanded")
    assert expanded.relationshipBonus == pytest.approx(0.38, abs=0.001), (
        f"Expected 0.38 for IMPORTS confidence=0.95, got {expanded.relationshipBonus}"
    )


# ---------------------------------------------------------------------------
# Test 2: USES confidence 0.75 → relationship bonus 0.30
# ---------------------------------------------------------------------------

def test_uses_confidence_075_gives_bonus_030():
    """
    A USES relationship with confidence=0.75 must produce
    relationshipBonus == round(0.75 * 0.4, 2) == 0.30 on the expanded file.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed", path="src/seed.py")
    _insert_file(conn, "f_expanded", path="src/expanded.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def compute(): pass")
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_expanded",
                         rel_type="USES", confidence=0.75)

    req = SearchRequest(query="compute", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    expanded = next(r for r in resp.results if r.fileId == "f_expanded")
    assert expanded.relationshipBonus == pytest.approx(0.30, abs=0.001), (
        f"Expected 0.30 for USES confidence=0.75, got {expanded.relationshipBonus}"
    )


# ---------------------------------------------------------------------------
# Test 3: Expansion works when seed is the relationship source
# ---------------------------------------------------------------------------

def test_expansion_seed_is_source():
    """
    Seed file is the source_id in the relationship → target file must be expanded.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_source", path="src/source.py")
    _insert_file(conn, "f_target", path="src/target.py")
    _insert_chunk(conn, "c1", "repo1", "f_source", 1, 30, "def query_handler(): pass")
    _insert_relationship(conn, "rel1", "repo1",
                         src_id="f_source", tgt_id="f_target",
                         rel_type="IMPORTS", confidence=0.95)

    req = SearchRequest(query="query", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    file_ids = [r.fileId for r in resp.results]
    assert "f_target" in file_ids, "Target file must be expanded when seed is source"


# ---------------------------------------------------------------------------
# Test 4: Expansion works when seed is the relationship target
# ---------------------------------------------------------------------------

def test_expansion_seed_is_target():
    """
    Seed file is the target_id in the relationship → source file must be expanded.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_source", path="src/source.py")
    _insert_file(conn, "f_target", path="src/target.py")
    _insert_chunk(conn, "c1", "repo1", "f_target", 1, 30, "def query_handler(): pass")
    _insert_relationship(conn, "rel1", "repo1",
                         src_id="f_source", tgt_id="f_target",
                         rel_type="IMPORTS", confidence=0.95)

    req = SearchRequest(query="query", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    file_ids = [r.fileId for r in resp.results]
    assert "f_source" in file_ids, "Source file must be expanded when seed is target"


# ---------------------------------------------------------------------------
# Test 5: Multiple relationships to same file → additive file scoring, max bonus
# ---------------------------------------------------------------------------

def test_multiple_relationships_additive_score_max_bonus():
    """
    Two relationships pointing to the same expanded file:
      - rel A: IMPORTS confidence=0.95  → score contribution 0.38
      - rel B: USES    confidence=0.75  → score contribution 0.30

    Expected file_scores addition: 0.38 + 0.30 = 0.68 (additive).
    Expected relationshipBonus: max(0.38, 0.30) = 0.38 (maximum of contributions).
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed1", path="src/seed1.py")
    _insert_file(conn, "f_seed2", path="src/seed2.py")
    _insert_file(conn, "f_shared", path="src/shared.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed1", 1, 30, "def compute(): pass")
    _insert_chunk(conn, "c2", "repo1", "f_seed2", 1, 30, "def compute_other(): pass")
    # Both seed files point to the same shared file
    _insert_relationship(conn, "rel1", "repo1",
                         src_id="f_seed1", tgt_id="f_shared",
                         rel_type="IMPORTS", confidence=0.95)
    _insert_relationship(conn, "rel2", "repo1",
                         src_id="f_seed2", tgt_id="f_shared",
                         rel_type="USES", confidence=0.75)

    req = SearchRequest(query="compute", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    shared = next(r for r in resp.results if r.fileId == "f_shared")
    # Additive total bonus applied to file_scores: 0.38 + 0.30 = 0.68
    # base_score for f_shared is 0.0 (no direct match), so file_score = 0.68
    # lexicalScore == file_score (before rel bonuses are separately tracked)
    assert shared.lexicalScore == pytest.approx(0.68, abs=0.01), (
        f"Additive file score expected ~0.68, got {shared.lexicalScore}"
    )
    # relationshipBonus = max of individual contributions = 0.38
    assert shared.relationshipBonus == pytest.approx(0.38, abs=0.001), (
        f"relationshipBonus must be max contribution 0.38, got {shared.relationshipBonus}"
    )


# ---------------------------------------------------------------------------
# Test 6: Reported relationshipBonus matches actual weighted bonus
# ---------------------------------------------------------------------------

def test_reported_relationship_bonus_matches_weighted_bonus():
    """
    Verify that the reported SearchResultItem.relationshipBonus is exactly
    confidence * 0.4, not any other constant.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed", path="src/seed.py")
    _insert_file(conn, "f_exp", path="src/exp.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def run(): pass")
    confidence = 0.6
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_exp",
                         rel_type="USES", confidence=confidence)

    req = SearchRequest(query="run", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    exp_result = next(r for r in resp.results if r.fileId == "f_exp")
    expected_bonus = round(confidence * 0.4, 2)
    assert exp_result.relationshipBonus == pytest.approx(expected_bonus, abs=0.001), (
        f"Expected relationshipBonus={expected_bonus}, got {exp_result.relationshipBonus}"
    )


# ---------------------------------------------------------------------------
# Test 7: Direct lexical matches still work unchanged
# ---------------------------------------------------------------------------

def test_direct_lexical_path_match_unchanged():
    """
    A file matched only via path token must still appear with
    relationshipBonus == 0.0 (no relationship expansion involved).
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_path", path="src/authentication_service.py")

    req = SearchRequest(query="authentication", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f_path")
    assert result.lexicalScore > 0.0, "Path-matched file must have positive lexical score"
    assert result.relationshipBonus == 0.0, (
        "Path-only match must have relationshipBonus == 0.0"
    )


def test_direct_lexical_component_match_unchanged():
    """
    A file matched via component name must still appear with
    relationshipBonus == 0.0.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_comp", path="src/utils.py")
    conn.execute(
        "INSERT INTO components (id, file_id, repository_id, name, type, start_line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("comp1", "f_comp", "repo1", "AuthManager", "class", 1, 50),
    )
    conn.commit()

    req = SearchRequest(query="AuthManager", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f_comp")
    assert result.lexicalScore > 0.0
    assert result.relationshipBonus == 0.0


# ---------------------------------------------------------------------------
# Test 8: relationshipAware=False → relationshipBonus == 0
# ---------------------------------------------------------------------------

def test_relationship_aware_false_gives_zero_bonus():
    """
    When relationshipAware=False, relationship expansion is disabled.
    The seed file's relationshipBonus must be 0.0.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f_seed", path="src/seed.py")
    _insert_file(conn, "f_other", path="src/other.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def compute(): pass")
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_other",
                         rel_type="IMPORTS", confidence=0.95)

    req = SearchRequest(query="compute", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    # f_other must NOT appear (no expansion)
    file_ids = [r.fileId for r in resp.results]
    assert "f_other" not in file_ids, "Expanded file must not appear when relationshipAware=False"

    # f_seed must have bonus 0.0
    seed_result = next(r for r in resp.results if r.fileId == "f_seed")
    assert seed_result.relationshipBonus == 0.0, (
        f"Expected 0.0 with relationshipAware=False, got {seed_result.relationshipBonus}"
    )


# ---------------------------------------------------------------------------
# Test 9: Existing content-chunk retrieval still works
# ---------------------------------------------------------------------------

def test_chunk_retrieval_unaffected():
    """
    Content-chunk matching must still find files by chunk text and report
    correct startLine/endLine/excerpt — unchanged by the confidence-weighting feature.
    """
    conn = _make_db()
    _insert_repo(conn)
    _insert_file(conn, "f1", path="src/unrelated.py")
    chunk_text = "def authenticate_user(token): pass"
    _insert_chunk(conn, "c1", "repo1", "f1", 15, 44, chunk_text)

    req = SearchRequest(query="authenticate", limit=10, relationshipAware=False)
    resp = RetrievalService.search(conn, "repo1", req)

    result = next(r for r in resp.results if r.fileId == "f1")
    assert result.startLine == 15
    assert result.endLine == 44
    assert result.excerpt == chunk_text
    assert result.lexicalScore >= 1.0
    assert result.relationshipBonus == 0.0


# ---------------------------------------------------------------------------
# Test 10: Score cap at 1.0 is preserved
# ---------------------------------------------------------------------------

def test_final_score_cap_at_1():
    """
    Even with a high confidence (1.0), the final score must never exceed 1.0.
    """
    conn = _make_db()
    _insert_repo(conn)
    # Seed matches path heavily AND has a relationship
    _insert_file(conn, "f_seed", path="src/compute_compute_compute.py")
    _insert_file(conn, "f_exp", path="src/expanded.py")
    _insert_chunk(conn, "c1", "repo1", "f_seed", 1, 30, "def compute(): pass")
    _insert_relationship(conn, "rel1", "repo1", "f_seed", "f_exp",
                         rel_type="IMPORTS", confidence=1.0)

    req = SearchRequest(query="compute", limit=10, relationshipAware=True)
    resp = RetrievalService.search(conn, "repo1", req)

    for r in resp.results:
        assert r.score <= 1.0, f"Score {r.score} for {r.fileId} exceeds cap of 1.0"
