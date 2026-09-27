"""
Tests for RelationshipIndex — the deterministic relationship query layer.

Covered assertions
------------------
* A imports B → B appears in A's outgoing relationships.
* A imports B → A appears in B's incoming relationships.
* One-hop neighbors are deterministic (same call, same result; correct set).
* Relationship type filtering works (IMPORTS vs EXPORTS).

Also tests:
- get_for_file returns relationships touching a file as source OR target.
- Empty result sets (no matches) return an empty list, not an error.
- NeighborListResponse excludes the queried node itself.
- Neighbor ordering is sorted (deterministic).
"""

from __future__ import annotations

import sqlite3
from typing import List

import pytest

from backend.app.models.domain import RelationshipType
from backend.app.services.relationships.index import RelationshipIndex


# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite DB seeded with known relationships
#
# Graph (file-level IMPORTS):
#
#   file_a  --IMPORTS-->  file_b
#   file_a  --IMPORTS-->  file_c
#   file_b  --IMPORTS-->  file_c
#   file_c  --EXPORTS-->  file_c   (self-export, to validate type filtering)
#
# node IDs:  "file_a", "file_b", "file_c"
# ---------------------------------------------------------------------------

REPO_ID = "repo_test_idx_001"

_RELS = [
    # (id, source_id, target_id, type, source_line)
    ("rel_a_b",  "file_a", "file_b", "IMPORTS", 1),
    ("rel_a_c",  "file_a", "file_c", "IMPORTS", 2),
    ("rel_b_c",  "file_b", "file_c", "IMPORTS", 1),
    ("rel_c_ex", "file_c", "file_c", "EXPORTS", 3),
]


@pytest.fixture()
def db() -> sqlite3.Connection:
    """Return a fresh in-memory connection seeded with the test graph."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE relationships (
            id           TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            source_type  TEXT NOT NULL DEFAULT 'file',
            source_id    TEXT NOT NULL,
            target_type  TEXT NOT NULL DEFAULT 'file',
            target_id    TEXT NOT NULL,
            type         TEXT NOT NULL,
            confidence   REAL DEFAULT 1.0,
            source_line  INTEGER,
            evidence     TEXT
        )
        """
    )
    for rel_id, src, tgt, rtype, line in _RELS:
        conn.execute(
            "INSERT INTO relationships VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rel_id, REPO_ID, "file", src, "file", tgt, rtype, 1.0, line, None),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ids(rels) -> List[str]:
    return [r.id for r in rels.relationships]


# ===========================================================================
# 1. Outgoing relationships
# ===========================================================================

class TestGetOutgoing:
    def test_a_imports_b__b_in_outgoing_of_a(self, db):
        """A imports B → B appears in A's outgoing relationships."""
        result = RelationshipIndex.get_outgoing(db, REPO_ID, "file_a")
        target_ids = [r.targetId for r in result.relationships]
        assert "file_b" in target_ids

    def test_outgoing_only_contains_edges_from_node(self, db):
        """get_outgoing must not return edges where file_a is the target."""
        result = RelationshipIndex.get_outgoing(db, REPO_ID, "file_a")
        for r in result.relationships:
            assert r.sourceId == "file_a"

    def test_outgoing_count_for_a(self, db):
        """file_a has exactly 2 outgoing IMPORTS edges."""
        result = RelationshipIndex.get_outgoing(db, REPO_ID, "file_a")
        assert len(result.relationships) == 2

    def test_outgoing_returns_dto_schema(self, db):
        result = RelationshipIndex.get_outgoing(db, REPO_ID, "file_a")
        r = result.relationships[0]
        assert hasattr(r, "id")
        assert hasattr(r, "sourceId")
        assert hasattr(r, "targetId")
        assert hasattr(r, "type")

    def test_outgoing_empty_for_leaf_node(self, db):
        """file_c has no outgoing IMPORTS (only an EXPORTS self-edge)."""
        result = RelationshipIndex.get_outgoing(db, REPO_ID, "file_c")
        imports = [r for r in result.relationships if r.type == RelationshipType.IMPORTS]
        assert imports == []

    def test_outgoing_unknown_node_returns_empty(self, db):
        result = RelationshipIndex.get_outgoing(db, REPO_ID, "does_not_exist")
        assert result.relationships == []


# ===========================================================================
# 2. Incoming relationships
# ===========================================================================

class TestGetIncoming:
    def test_a_imports_b__a_in_incoming_of_b(self, db):
        """A imports B → A appears in B's incoming relationships."""
        result = RelationshipIndex.get_incoming(db, REPO_ID, "file_b")
        source_ids = [r.sourceId for r in result.relationships]
        assert "file_a" in source_ids

    def test_incoming_only_contains_edges_to_node(self, db):
        result = RelationshipIndex.get_incoming(db, REPO_ID, "file_c")
        for r in result.relationships:
            assert r.targetId == "file_c"

    def test_incoming_count_for_c(self, db):
        """file_c is the target of: rel_a_c, rel_b_c, rel_c_ex → 3 edges."""
        result = RelationshipIndex.get_incoming(db, REPO_ID, "file_c")
        assert len(result.relationships) == 3

    def test_incoming_empty_for_root_node(self, db):
        """file_a is never a target → empty incoming."""
        result = RelationshipIndex.get_incoming(db, REPO_ID, "file_a")
        assert result.relationships == []

    def test_incoming_unknown_node_returns_empty(self, db):
        result = RelationshipIndex.get_incoming(db, REPO_ID, "does_not_exist")
        assert result.relationships == []


# ===========================================================================
# 3. One-hop neighbors (determinism)
# ===========================================================================

class TestGetNeighbors:
    def test_neighbors_of_a_are_b_and_c(self, db):
        """file_a's one-hop neighbors are file_b and file_c (outgoing edges)."""
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "file_a")
        assert set(result.neighborIds) == {"file_b", "file_c"}

    def test_neighbors_of_b(self, db):
        """file_b: outgoing to file_c; incoming from file_a → neighbors are {file_a, file_c}."""
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "file_b")
        assert set(result.neighborIds) == {"file_a", "file_c"}

    def test_neighbors_are_deterministic(self, db):
        """Calling get_neighbors twice on the same DB must return identical results."""
        result1 = RelationshipIndex.get_neighbors(db, REPO_ID, "file_b")
        result2 = RelationshipIndex.get_neighbors(db, REPO_ID, "file_b")
        assert result1.neighborIds == result2.neighborIds

    def test_neighbors_sorted(self, db):
        """neighborIds must be sorted for deterministic ordering."""
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "file_b")
        assert result.neighborIds == sorted(result.neighborIds)

    def test_queried_node_not_in_neighbors(self, db):
        """The queried node itself must not appear in its own neighbor list."""
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "file_c")
        assert "file_c" not in result.neighborIds

    def test_neighbors_no_duplicates(self, db):
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "file_b")
        assert len(result.neighborIds) == len(set(result.neighborIds))

    def test_isolated_node_returns_empty_neighbors(self, db):
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "does_not_exist")
        assert result.neighborIds == []

    def test_response_carries_node_id(self, db):
        result = RelationshipIndex.get_neighbors(db, REPO_ID, "file_a")
        assert result.nodeId == "file_a"


# ===========================================================================
# 4. Relationship type filtering
# ===========================================================================

class TestGetByType:
    def test_imports_returns_only_imports(self, db):
        """Filtering by IMPORTS must not return EXPORTS edges."""
        result = RelationshipIndex.get_by_type(db, REPO_ID, RelationshipType.IMPORTS)
        for r in result.relationships:
            assert r.type == RelationshipType.IMPORTS

    def test_exports_returns_only_exports(self, db):
        result = RelationshipIndex.get_by_type(db, REPO_ID, RelationshipType.EXPORTS)
        for r in result.relationships:
            assert r.type == RelationshipType.EXPORTS

    def test_imports_count(self, db):
        """There are exactly 3 IMPORTS edges in the test graph."""
        result = RelationshipIndex.get_by_type(db, REPO_ID, RelationshipType.IMPORTS)
        assert len(result.relationships) == 3

    def test_exports_count(self, db):
        """There is exactly 1 EXPORTS edge in the test graph."""
        result = RelationshipIndex.get_by_type(db, REPO_ID, RelationshipType.EXPORTS)
        assert len(result.relationships) == 1

    def test_uses_type_returns_empty_when_none_present(self, db):
        result = RelationshipIndex.get_by_type(db, REPO_ID, RelationshipType.USES)
        assert result.relationships == []


# ===========================================================================
# 5. Relationships for a file / component
# ===========================================================================

class TestGetForFile:
    def test_file_b_appears_as_both_source_and_target(self, db):
        """file_b is source in rel_b_c and target in rel_a_b → both returned."""
        result = RelationshipIndex.get_for_file(db, REPO_ID, "file_b")
        ids = {r.id for r in result.relationships}
        assert "rel_a_b" in ids   # file_b as target
        assert "rel_b_c" in ids   # file_b as source

    def test_file_a_only_as_source(self, db):
        result = RelationshipIndex.get_for_file(db, REPO_ID, "file_a")
        for r in result.relationships:
            assert r.sourceId == "file_a" or r.targetId == "file_a"

    def test_file_a_relationships_count(self, db):
        """file_a appears as source of rel_a_b and rel_a_c → 2 edges."""
        result = RelationshipIndex.get_for_file(db, REPO_ID, "file_a")
        assert len(result.relationships) == 2

    def test_file_c_relationships_includes_self_loop(self, db):
        """file_c is involved in rel_a_c, rel_b_c, and the self-export rel_c_ex."""
        result = RelationshipIndex.get_for_file(db, REPO_ID, "file_c")
        ids = {r.id for r in result.relationships}
        assert {"rel_a_c", "rel_b_c", "rel_c_ex"}.issubset(ids)

    def test_unknown_file_returns_empty(self, db):
        result = RelationshipIndex.get_for_file(db, REPO_ID, "does_not_exist")
        assert result.relationships == []
