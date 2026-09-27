"""
Tests proving that RelationshipExtractor produces records that are correctly
shaped for persistence into the ``relationships`` DB table, and that
analysis_service.py can INSERT them without KeyError.

Requirements tested
-------------------
1. Python IMPORTS relationship is persisted (has all DB columns).
2. JS/TS IMPORTS relationship is persisted.
3. EXPORTS relationship is persisted.
4. source_id is the actual source file ID (not a path string).
5. Resolved target_id is the actual target file ID.
6. Unresolved imports do NOT produce a fake file ID as target_id.
7. Relationship IDs remain deterministic (same input → same ID).
8. Repeated extraction does not create duplicate relationship records
   when INSERTed into a real SQLite table using the deterministic IDs.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, Dict, List

import pytest

from backend.app.models.domain import RelationshipType
from backend.app.services.relationships.extractor import RelationshipExtractor, _rel_id

# ---------------------------------------------------------------------------
# Shared test fixture: a minimal two-file Python repo
# ---------------------------------------------------------------------------
#
# Files:
#   src/utils.py   – exported symbol, imported by src/service.py
#   src/service.py – imports src.utils (intra-repo) and os (external)
#
# File IDs are deterministic strings (not UUIDs) so tests can assert on them.

REPO_ID = "repo_persist_test"
FILE_ID_UTILS = "file_utils_0001"
FILE_ID_SERVICE = "file_service_001"
FILE_ID_UTILS_TS = "file_utils_ts001"
FILE_ID_APP_TSX = "file_app_tsx001"


PY_FILES_MAP: Dict[str, Dict[str, Any]] = {
    FILE_ID_UTILS: {"relative_path": "src/utils.py"},
    FILE_ID_SERVICE: {"relative_path": "src/service.py"},
}

PY_FILE_CONTENTS: Dict[str, str] = {
    FILE_ID_UTILS: '__all__ = ["helper"]\ndef helper(x): return x\n',
    FILE_ID_SERVICE: "from src.utils import helper\nimport os\n",
}

TS_FILES_MAP: Dict[str, Dict[str, Any]] = {
    FILE_ID_UTILS_TS: {"relative_path": "frontend/utils.ts"},
    FILE_ID_APP_TSX: {"relative_path": "frontend/app.tsx"},
}

TS_FILE_CONTENTS: Dict[str, str] = {
    FILE_ID_UTILS_TS: "export function formatDate(d: Date): string { return ''; }\n",
    FILE_ID_APP_TSX: "import React from 'react';\nimport { formatDate } from './utils';\n",
}


def _run_py() -> List[Dict[str, Any]]:
    return RelationshipExtractor.extract_relationships(
        repo_id=REPO_ID,
        files_map=PY_FILES_MAP,
        components_by_file={},
        file_contents=PY_FILE_CONTENTS,
    )


def _run_ts() -> List[Dict[str, Any]]:
    return RelationshipExtractor.extract_relationships(
        repo_id=REPO_ID,
        files_map=TS_FILES_MAP,
        components_by_file={},
        file_contents=TS_FILE_CONTENTS,
    )


def _by(rels, **kw):
    return [r for r in rels if all(r.get(k) == v for k, v in kw.items())]


def _one(rels, **kw):
    found = _by(rels, **kw)
    assert len(found) == 1, f"Expected 1 match for {kw}, got {len(found)}: {found}"
    return found[0]


# ---------------------------------------------------------------------------
# In-memory SQLite fixture for persistence round-trip tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db() -> sqlite3.Connection:
    """Minimal in-memory DB with only the relationships table."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE relationships (
            id           TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            source_type  TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            target_type  TEXT NOT NULL,
            target_id    TEXT NOT NULL,
            type         TEXT NOT NULL,
            confidence   REAL DEFAULT 1.0,
            source_line  INTEGER,
            evidence     TEXT
        )
        """
    )
    conn.commit()
    return conn


def _insert_rels(conn: sqlite3.Connection, rels: List[Dict[str, Any]]) -> None:
    """Mirror exactly what analysis_service.py does."""
    for rel in rels:
        conn.execute(
            """
            INSERT INTO relationships
                (id, repository_id, source_type, source_id, target_type, target_id,
                 type, confidence, source_line, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel["id"],
                rel["repository_id"],
                rel["source_type"],
                rel["source_id"],
                rel["target_type"],
                rel["target_id"],
                rel["type"].value if hasattr(rel["type"], "value") else rel["type"],
                rel["confidence"],
                rel["source_line"],
                rel["evidence"],
            ),
        )
    conn.commit()


# ===========================================================================
# 1. Python IMPORTS is persisted (has all required DB columns)
# ===========================================================================

class TestPythonImportsPersisted:
    def setup_method(self):
        self.rels = _run_py()

    def test_python_imports_exists(self):
        """from src.utils import helper → IMPORTS record is produced."""
        matches = _by(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        assert len(matches) == 1

    def test_python_imports_has_all_db_columns(self):
        r = _one(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        for col in ("id", "repository_id", "source_type", "source_id",
                    "target_type", "target_id", "type", "confidence",
                    "source_line", "evidence"):
            assert col in r, f"Missing DB column: {col}"

    def test_python_imports_can_be_inserted(self, mem_db):
        """All Python IMPORTS records can be INSERTed without error."""
        py_imports = _by(self.rels, type=RelationshipType.IMPORTS)
        _insert_rels(mem_db, py_imports)  # must not raise
        count = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count == len(py_imports)


# ===========================================================================
# 2. JS/TS IMPORTS is persisted
# ===========================================================================

class TestJSImportsPersisted:
    def setup_method(self):
        self.rels = _run_ts()

    def test_ts_imports_react_exists(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="react")
        assert r["type"] == RelationshipType.IMPORTS

    def test_ts_imports_utils_exists(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="./utils")
        assert r["type"] == RelationshipType.IMPORTS

    def test_ts_imports_has_all_db_columns(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="./utils")
        for col in ("id", "repository_id", "source_type", "source_id",
                    "target_type", "target_id", "type", "confidence",
                    "source_line", "evidence"):
            assert col in r, f"Missing DB column: {col}"

    def test_ts_imports_can_be_inserted(self, mem_db):
        ts_imports = _by(self.rels, type=RelationshipType.IMPORTS)
        _insert_rels(mem_db, ts_imports)
        count = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count == len(ts_imports)


# ===========================================================================
# 3. EXPORTS is persisted
# ===========================================================================

class TestExportsPersisted:
    def test_python_exports_persisted(self, mem_db):
        rels = _run_py()
        exports = _by(rels, type=RelationshipType.EXPORTS)
        assert len(exports) >= 1, "Expected at least one EXPORTS record"
        _insert_rels(mem_db, exports)  # must not raise
        count = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count == len(exports)

    def test_ts_exports_persisted(self, mem_db):
        rels = _run_ts()
        exports = _by(rels, type=RelationshipType.EXPORTS)
        assert len(exports) >= 1
        _insert_rels(mem_db, exports)
        count = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count == len(exports)

    def test_exports_has_all_db_columns(self):
        rels = _run_py()
        r = _one(rels, source_file="src/utils.py", type=RelationshipType.EXPORTS, target_spec="helper")
        for col in ("id", "repository_id", "source_type", "source_id",
                    "target_type", "target_id", "type", "confidence",
                    "source_line", "evidence"):
            assert col in r, f"Missing DB column: {col}"


# ===========================================================================
# 4. source_id is the actual file ID
# ===========================================================================

class TestSourceIdIsFileId:
    def test_python_imports_source_id_is_file_id(self):
        rels = _run_py()
        r = _one(rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        assert r["source_id"] == FILE_ID_SERVICE, (
            f"source_id should be file ID '{FILE_ID_SERVICE}', got '{r['source_id']}'"
        )

    def test_ts_imports_source_id_is_file_id(self):
        rels = _run_ts()
        r = _one(rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="./utils")
        assert r["source_id"] == FILE_ID_APP_TSX

    def test_exports_source_id_is_file_id(self):
        rels = _run_py()
        r = _one(rels, source_file="src/utils.py", type=RelationshipType.EXPORTS, target_spec="helper")
        assert r["source_id"] == FILE_ID_UTILS

    def test_source_type_is_always_file(self):
        rels = _run_py() + _run_ts()
        for r in rels:
            assert r["source_type"] == "file", f"source_type should be 'file', got: {r['source_type']}"


# ===========================================================================
# 5. Resolved target_id is the actual target file ID
# ===========================================================================

class TestResolvedTargetIdIsFileId:
    def test_python_resolved_import_target_id_is_file_id(self):
        rels = _run_py()
        r = _one(rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        assert r["target_resolved"] is True
        assert r["target_id"] == FILE_ID_UTILS, (
            f"Resolved target_id should be file ID '{FILE_ID_UTILS}', got '{r['target_id']}'"
        )
        assert r["target_type"] == "file"

    def test_ts_resolved_import_target_id_is_file_id(self):
        rels = _run_ts()
        r = _one(rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="./utils")
        assert r["target_resolved"] is True
        assert r["target_id"] == FILE_ID_UTILS_TS
        assert r["target_type"] == "file"

    def test_exports_target_id_is_source_file_id(self):
        """For EXPORTS the target is the same file — target_id must equal source_id."""
        rels = _run_py()
        r = _one(rels, source_file="src/utils.py", type=RelationshipType.EXPORTS, target_spec="helper")
        assert r["target_id"] == FILE_ID_UTILS
        assert r["target_type"] == "file"


# ===========================================================================
# 6. Unresolved imports do NOT produce a fake file ID as target_id
# ===========================================================================

class TestUnresolvedImportNoFakeFileId:
    def test_stdlib_import_target_id_is_not_a_file_id(self):
        rels = _run_py()
        r = _one(rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert r["target_resolved"] is False
        # Must not look like a file ID
        assert not r["target_id"].startswith("file_"), (
            f"Unresolved import must not have a file ID as target_id, got: '{r['target_id']}'"
        )

    def test_unresolved_target_type_is_external(self):
        rels = _run_py()
        r = _one(rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert r["target_type"] == "external"

    def test_unresolved_target_id_is_the_specifier(self):
        """target_id for an unresolved import must be the raw specifier string."""
        rels = _run_py()
        r = _one(rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert r["target_id"] == "os"

    def test_ts_unresolved_import_target_type_external(self):
        rels = _run_ts()
        r = _one(rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="react")
        assert r["target_resolved"] is False
        assert r["target_type"] == "external"
        assert not r["target_id"].startswith("file_")

    def test_unresolved_can_still_be_inserted(self, mem_db):
        """Unresolved imports must be insertable — target_id NOT NULL constraint satisfied."""
        rels = _run_py()
        unresolved = [r for r in rels if not r.get("target_resolved")]
        assert unresolved, "Expected at least one unresolved import"
        _insert_rels(mem_db, unresolved)  # must not raise IntegrityError
        count = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count == len(unresolved)


# ===========================================================================
# 7. Relationship IDs remain deterministic
# ===========================================================================

class TestDeterministicIds:
    def test_same_input_produces_same_ids(self):
        ids1 = [r["id"] for r in _run_py()]
        ids2 = [r["id"] for r in _run_py()]
        assert ids1 == ids2

    def test_id_formula_unchanged(self):
        """ID must still be _rel_id(repo_id, source_path, type, spec, line)."""
        rels = _run_py()
        r = _one(rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        expected = _rel_id(REPO_ID, "src/service.py", "IMPORTS", "src.utils", r["source_line"])
        assert r["id"] == expected

    def test_new_fields_do_not_change_id(self):
        """Adding source_id/target_id/confidence/evidence must NOT alter the ID."""
        rels = _run_py()
        for r in rels:
            recomputed = _rel_id(
                REPO_ID,
                r["source_file"],
                r["type"].value if hasattr(r["type"], "value") else r["type"],
                r["target_spec"],
                r["source_line"],
            )
            assert r["id"] == recomputed, (
                f"ID drift detected for {r['source_file']} -> {r['target_spec']}: "
                f"stored={r['id']} recomputed={recomputed}"
            )


# ===========================================================================
# 8. Repeated extraction does not create duplicate relationship records
# ===========================================================================

class TestNoDuplicatesOnRepeatedExtraction:
    def test_second_insert_raises_integrity_error(self, mem_db):
        """
        Inserting the same deterministic records twice must raise IntegrityError
        on the second INSERT (PRIMARY KEY collision), proving deduplication works
        at the DB level when callers use the deterministic IDs correctly.
        """
        rels = _run_py()
        _insert_rels(mem_db, rels)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_rels(mem_db, rels)

    def test_insert_or_ignore_prevents_duplicates(self, mem_db):
        """
        Using INSERT OR IGNORE with deterministic IDs yields exactly the same
        count after a second run — no duplicates are created.
        """
        rels = _run_py()

        def _upsert(conn, rows):
            for rel in rows:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO relationships
                        (id, repository_id, source_type, source_id, target_type, target_id,
                         type, confidence, source_line, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rel["id"], rel["repository_id"],
                        rel["source_type"], rel["source_id"],
                        rel["target_type"], rel["target_id"],
                        rel["type"].value if hasattr(rel["type"], "value") else rel["type"],
                        rel["confidence"], rel["source_line"], rel["evidence"],
                    ),
                )
            conn.commit()

        _upsert(mem_db, rels)
        count_after_first = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        _upsert(mem_db, rels)
        count_after_second = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count_after_first == count_after_second, (
            f"Duplicate rows created: {count_after_first} → {count_after_second}"
        )

    def test_record_count_matches_extractor_output(self, mem_db):
        rels = _run_py()
        _insert_rels(mem_db, rels)
        count = mem_db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        assert count == len(rels)
