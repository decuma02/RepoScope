"""
Tests for the deterministic P0 relationship extractor.

Covers:
  1. Direct import (Python ``import X``)
  2. Multiple imports in one statement (``from X import A, B``)
  3. Exported symbol (Python ``__all__``, JS ``export``)
  4. Unresolved import (third-party / stdlib module not in the repo)
  5. Relationship source line accuracy

Also tests:
  - JS/TS IMPORTS and EXPORTS
  - Relative Python imports
  - Relative JS imports (including ``../`` traversal)
  - Determinism: same input always produces identical record list
  - Stable IDs: IDs do not change across runs
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import pytest

from backend.app.models.domain import RelationshipType
from backend.app.services.relationships.extractor import (
    RelationshipExtractor,
    _python_exports,
    _python_imports,
    _js_exports,
    _js_imports,
    _rel_id,
    _resolve_python_import,
    _resolve_js_import,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ID = "repo_test_rel_001"


def _file(rel_path: str) -> Dict[str, Any]:
    return {"relative_path": rel_path}


def _run(
    files: Dict[str, str],  # rel_path -> content
    repo_id: str = REPO_ID,
) -> List[Dict[str, Any]]:
    """Build files_map / file_contents from a simple rel_path→content dict."""
    files_map: Dict[str, Dict[str, Any]] = {}
    file_contents: Dict[str, str] = {}
    for i, (rel_path, content) in enumerate(sorted(files.items())):
        fid = f"f{i:04d}"
        files_map[fid] = _file(rel_path)
        file_contents[fid] = content
    return RelationshipExtractor.extract_relationships(
        repo_id=repo_id,
        files_map=files_map,
        components_by_file={},
        file_contents=file_contents,
    )


def _by(rels: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
    """Filter relationships by arbitrary field values."""
    result = []
    for r in rels:
        if all(r.get(k) == v for k, v in kwargs.items()):
            result.append(r)
    return result


def _one(rels: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    found = _by(rels, **kwargs)
    assert len(found) == 1, f"Expected 1 match for {kwargs}, got {len(found)}: {found}"
    return found[0]


# ===========================================================================
# Demo repository fixture
# ---------------------------------------------------------------------------
# Layout:
#
#   src/utils.py          – defines helper(), exported via __all__
#   src/models.py         – defines User, exported via __all__
#   src/service.py        – imports utils.helper and models.User
#   src/api.py            – imports service, plus stdlib 'os' and 'json'
#   src/subpkg/__init__.py– empty
#   src/subpkg/worker.py  – relative import: from .. import service
#   frontend/utils.ts     – exports formatDate, formatTime
#   frontend/app.tsx      – imports from './utils', and from 'react' (unresolved)
# ===========================================================================

DEMO_FILES: Dict[str, str] = {
    "src/utils.py": '''\
"""Utility helpers."""

__all__ = ["helper"]


def helper(x):
    """Do something."""
    return x
''',
    "src/models.py": '''\
"""Domain models."""

__all__ = ["User"]


class User:
    """A user."""
    def __init__(self, name: str):
        self.name = name
''',
    "src/service.py": '''\
"""Service layer."""
from src.utils import helper
from src.models import User


def create_user(name: str) -> User:
    return User(helper(name))
''',
    "src/api.py": '''\
"""API layer."""
import os
import json
from src.service import create_user


def handle(request):
    return create_user(json.loads(request))
''',
    "src/subpkg/__init__.py": "",
    "src/subpkg/worker.py": '''\
"""Worker in a subpackage."""
from .. import service


def run():
    return service.create_user("worker")
''',
    "frontend/utils.ts": '''\
export function formatDate(d: Date): string {
    return d.toISOString().slice(0, 10);
}

export function formatTime(d: Date): string {
    return d.toISOString().slice(11, 19);
}

export const VERSION = "2.0";
''',
    "frontend/app.tsx": '''\
import React from 'react';
import { formatDate, formatTime } from './utils';

export default function App() {
    return <div>{formatDate(new Date())}</div>;
}
''',
}


# ===========================================================================
# 1. Direct import
# ===========================================================================

class TestDirectImport:
    def setup_method(self):
        self.rels = _run(DEMO_FILES)

    def test_direct_import_os_exists(self):
        """import os in src/api.py produces an IMPORTS record."""
        matches = _by(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert len(matches) == 1

    def test_direct_import_type(self):
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert r["type"] == RelationshipType.IMPORTS

    def test_direct_import_json_exists(self):
        """import json in src/api.py is also captured."""
        _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="json")

    def test_direct_import_resolves_intra_repo(self):
        """from src.service import create_user resolves to src/service.py."""
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="src.service")
        assert r["target_file"] == "src/service.py"
        assert r["target_resolved"] is True


# ===========================================================================
# 2. Multiple imports
# ===========================================================================

class TestMultipleImports:
    def setup_method(self):
        self.rels = _run(DEMO_FILES)

    def test_from_utils_import_helper_exists(self):
        """from src.utils import helper → one IMPORTS record."""
        r = _one(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        assert r["target_file"] == "src/utils.py"

    def test_from_models_import_user_exists(self):
        r = _one(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.models")
        assert r["target_file"] == "src/models.py"

    def test_api_has_three_imports(self):
        """src/api.py has 3 IMPORTS: os, json, src.service."""
        imports = _by(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS)
        specs = {r["target_spec"] for r in imports}
        assert {"os", "json", "src.service"}.issubset(specs)

    def test_service_has_two_imports(self):
        imports = _by(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS)
        assert len(imports) == 2


# ===========================================================================
# 3. Exported symbol
# ===========================================================================

class TestExportedSymbol:
    def setup_method(self):
        self.rels = _run(DEMO_FILES)

    def test_utils_exports_helper(self):
        """src/utils.py __all__ = ['helper'] → EXPORTS record for helper."""
        r = _one(self.rels, source_file="src/utils.py", type=RelationshipType.EXPORTS, target_spec="helper")
        assert r["target_resolved"] is True
        assert r["target_file"] == "src/utils.py"

    def test_models_exports_user(self):
        r = _one(self.rels, source_file="src/models.py", type=RelationshipType.EXPORTS, target_spec="User")
        assert r["target_resolved"] is True

    def test_js_exports_format_date(self):
        r = _one(self.rels, source_file="frontend/utils.ts", type=RelationshipType.EXPORTS, target_spec="formatDate")
        assert r["target_resolved"] is True
        assert r["target_file"] == "frontend/utils.ts"

    def test_js_exports_format_time(self):
        _one(self.rels, source_file="frontend/utils.ts", type=RelationshipType.EXPORTS, target_spec="formatTime")

    def test_js_exports_version_const(self):
        _one(self.rels, source_file="frontend/utils.ts", type=RelationshipType.EXPORTS, target_spec="VERSION")

    def test_tsx_default_export(self):
        """export default function App in app.tsx produces EXPORTS record."""
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.EXPORTS, target_spec="App")
        assert r["target_resolved"] is True

    def test_service_has_no_exports(self):
        """src/service.py has no __all__, so no EXPORTS records."""
        exports = _by(self.rels, source_file="src/service.py", type=RelationshipType.EXPORTS)
        assert exports == []


# ===========================================================================
# 4. Unresolved import
# ===========================================================================

class TestUnresolvedImport:
    def setup_method(self):
        self.rels = _run(DEMO_FILES)

    def test_os_is_unresolved(self):
        """stdlib 'os' is not in the repo → target_resolved=False."""
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert r["target_resolved"] is False
        assert r["target_file"] is None

    def test_json_is_unresolved(self):
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="json")
        assert r["target_resolved"] is False

    def test_react_is_unresolved(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="react")
        assert r["target_resolved"] is False
        assert r["target_file"] is None

    def test_unresolved_record_still_has_required_fields(self):
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="os")
        for field in ("id", "repository_id", "type", "source_file", "source_line", "target_spec"):
            assert field in r, f"Missing field: {field}"

    def test_relative_import_resolves_when_target_exists(self):
        """from .. import service in src/subpkg/worker.py should resolve."""
        # target_spec for "from .. import service" is "..service"
        r = _one(self.rels, source_file="src/subpkg/worker.py", type=RelationshipType.IMPORTS, target_spec="..service")
        assert r["target_resolved"] is True
        assert r["target_file"] == "src/service.py"


# ===========================================================================
# 5. Relationship source line
# ===========================================================================

class TestSourceLine:
    def setup_method(self):
        self.rels = _run(DEMO_FILES)

    def test_utils_all_on_line_3(self):
        """``__all__ = ['helper']`` is on line 3 of src/utils.py."""
        r = _one(self.rels, source_file="src/utils.py", type=RelationshipType.EXPORTS, target_spec="helper")
        assert r["source_line"] == 3

    def test_service_import_utils_line(self):
        """from src.utils import helper is on line 2 of src/service.py."""
        r = _one(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.utils")
        assert r["source_line"] == 2

    def test_service_import_models_line(self):
        """from src.models import User is on line 3 of src/service.py."""
        r = _one(self.rels, source_file="src/service.py", type=RelationshipType.IMPORTS, target_spec="src.models")
        assert r["source_line"] == 3

    def test_api_import_os_line(self):
        """import os is on line 2 of src/api.py."""
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="os")
        assert r["source_line"] == 2

    def test_api_import_json_line(self):
        r = _one(self.rels, source_file="src/api.py", type=RelationshipType.IMPORTS, target_spec="json")
        assert r["source_line"] == 3

    def test_js_import_react_line(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="react")
        assert r["source_line"] == 1

    def test_js_import_utils_line(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="./utils")
        assert r["source_line"] == 2

    def test_tsx_export_app_line(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.EXPORTS, target_spec="App")
        assert r["source_line"] == 4

    def test_source_line_always_positive(self):
        for r in self.rels:
            assert r["source_line"] >= 1, f"source_line < 1: {r}"


# ===========================================================================
# Determinism & stable IDs
# ===========================================================================

class TestDeterminism:
    def test_same_input_same_output(self):
        """Running extract_relationships twice yields identical result."""
        rels1 = _run(DEMO_FILES)
        rels2 = _run(DEMO_FILES)
        assert rels1 == rels2

    def test_ids_are_stable(self):
        rels1 = _run(DEMO_FILES)
        rels2 = _run(DEMO_FILES)
        ids1 = [r["id"] for r in rels1]
        ids2 = [r["id"] for r in rels2]
        assert ids1 == ids2

    def test_output_is_sorted(self):
        """Output must be sorted by (source_file, source_line, type, target_spec)."""
        rels = _run(DEMO_FILES)
        keys = [(r["source_file"], r["source_line"], r["type"], r["target_spec"]) for r in rels]
        assert keys == sorted(keys)

    def test_id_format(self):
        rels = _run(DEMO_FILES)
        for r in rels:
            assert r["id"].startswith("rel_"), f"Bad id format: {r['id']}"
            assert len(r["id"]) == 4 + 16  # "rel_" + 16 hex chars

    def test_stable_id_matches_formula(self):
        """Spot-check that _rel_id produces the correct prefix."""
        rel_type = "IMPORTS"
        rid = _rel_id(REPO_ID, "src/api.py", rel_type, "os", 2)
        key = f"{REPO_ID}\x00src/api.py\x00{rel_type}\x00os\x002"
        expected = "rel_" + hashlib.sha1(key.encode()).hexdigest()[:16]
        assert rid == expected

    def test_no_uuid_in_ids(self):
        """IDs must not be random (UUID-based), they must be deterministic."""
        rels1 = _run(DEMO_FILES)
        rels2 = _run(DEMO_FILES)
        assert [r["id"] for r in rels1] == [r["id"] for r in rels2]


# ===========================================================================
# JS/TS specific tests
# ===========================================================================

class TestJSTSRelationships:
    def setup_method(self):
        self.rels = _run(DEMO_FILES)

    def test_app_tsx_imports_utils(self):
        """frontend/app.tsx imports from './utils' which resolves to frontend/utils.ts."""
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="./utils")
        assert r["target_resolved"] is True
        assert r["target_file"] == "frontend/utils.ts"

    def test_app_tsx_imports_react_unresolved(self):
        r = _one(self.rels, source_file="frontend/app.tsx", type=RelationshipType.IMPORTS, target_spec="react")
        assert r["target_resolved"] is False

    def test_utils_ts_has_three_exports(self):
        exports = _by(self.rels, source_file="frontend/utils.ts", type=RelationshipType.EXPORTS)
        names = {r["target_spec"] for r in exports}
        assert names == {"formatDate", "formatTime", "VERSION"}

    def test_app_tsx_has_one_export(self):
        exports = _by(self.rels, source_file="frontend/app.tsx", type=RelationshipType.EXPORTS)
        assert len(exports) == 1
        assert exports[0]["target_spec"] == "App"


# ===========================================================================
# Unit tests for internal helpers
# ===========================================================================

class TestPythonImportsHelper:
    def test_direct_import(self):
        imps = _python_imports("import os\n")
        assert len(imps) == 1
        assert imps[0]["module"] == "os"
        assert imps[0]["source_line"] == 1
        assert imps[0]["is_relative"] is False

    def test_from_import(self):
        imps = _python_imports("from pathlib import Path\n")
        assert len(imps) == 1
        assert imps[0]["module"] == "pathlib"
        assert imps[0]["names"] == ["Path"]

    def test_multiple_names(self):
        imps = _python_imports("from os.path import join, exists\n")
        assert imps[0]["names"] == ["join", "exists"]

    def test_relative_import(self):
        imps = _python_imports("from .. import service\n")
        assert imps[0]["level"] == 2
        assert imps[0]["is_relative"] is True

    def test_sorted_by_line(self):
        src = "import b\nimport a\n"
        imps = _python_imports(src)
        lines = [i["source_line"] for i in imps]
        assert lines == sorted(lines)


class TestPythonExportsHelper:
    def test_all_single(self):
        src = '__all__ = ["helper"]\n'
        exps = _python_exports(src)
        assert exps[0]["name"] == "helper"
        assert exps[0]["source_line"] == 1

    def test_all_multiple(self):
        src = '__all__ = ["A", "B", "C"]\n'
        exps = _python_exports(src)
        names = {e["name"] for e in exps}
        assert names == {"A", "B", "C"}

    def test_no_all(self):
        src = "def foo(): pass\n"
        assert _python_exports(src) == []

    def test_syntax_error_returns_empty(self):
        assert _python_exports("!!!invalid python!!!") == []


class TestJsImportsHelper:
    def test_es_import_from(self):
        imps = _js_imports("import React from 'react';\n")
        assert imps[0]["module"] == "react"
        assert imps[0]["source_line"] == 1

    def test_named_import(self):
        imps = _js_imports("import { useState } from 'react';\n")
        assert imps[0]["module"] == "react"

    def test_side_effect_import(self):
        imps = _js_imports("import './styles.css';\n")
        assert imps[0]["module"] == "./styles.css"

    def test_require(self):
        imps = _js_imports("const path = require('path');\n")
        assert imps[0]["module"] == "path"

    def test_multiple_imports_sorted(self):
        src = "import B from 'b';\nimport A from 'a';\n"
        imps = _js_imports(src)
        lines = [i["source_line"] for i in imps]
        assert lines == sorted(lines)


class TestJsExportsHelper:
    def test_export_function(self):
        exps = _js_exports("export function foo() {}\n")
        assert exps[0]["name"] == "foo"

    def test_export_const(self):
        exps = _js_exports("export const BAR = 1;\n")
        assert exps[0]["name"] == "BAR"

    def test_export_default_function(self):
        exps = _js_exports("export default function App() {}\n")
        assert exps[0]["name"] == "App"

    def test_export_brace(self):
        exps = _js_exports("export { foo, bar };\n")
        names = {e["name"] for e in exps}
        assert names == {"foo", "bar"}

    def test_export_class(self):
        exps = _js_exports("export class MyClass {}\n")
        assert exps[0]["name"] == "MyClass"


class TestResolvers:
    def test_python_resolves_absolute(self):
        path_map = {"src/utils.py": "f001"}
        fid = _resolve_python_import("src.utils", "src/service.py", path_map, level=0)
        assert fid == "f001"

    def test_python_relative_level1(self):
        path_map = {"src/utils.py": "f001"}
        fid = _resolve_python_import("utils", "src/service.py", path_map, level=1)
        assert fid == "f001"

    def test_python_relative_level2(self):
        path_map = {"src/service.py": "f002"}
        fid = _resolve_python_import("service", "src/subpkg/worker.py", path_map, level=2)
        assert fid == "f002"

    def test_python_unresolvable(self):
        assert _resolve_python_import("os", "src/api.py", {}, level=0) is None

    def test_js_relative_same_dir(self):
        path_map = {"frontend/utils.ts": "f010"}
        fid = _resolve_js_import("./utils", "frontend/app.tsx", path_map)
        assert fid == "f010"

    def test_js_parent_dir(self):
        path_map = {"src/utils.ts": "f011"}
        fid = _resolve_js_import("../utils", "src/sub/comp.tsx", path_map)
        assert fid == "f011"

    def test_js_non_relative_unresolved(self):
        assert _resolve_js_import("react", "frontend/app.tsx", {}) is None
