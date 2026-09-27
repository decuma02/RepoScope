"""
Unit tests for lightweight structure extraction.

Covers:
- Python: top-level functions, classes, methods (AST)
- Python: __all__ export detection
- Python: async functions and methods
- Python: regex fallback (syntax-error source)
- JS/TS: named functions, arrow functions, classes, export detection
- JS/TS: class methods
- Directory record extraction
- Line range accuracy (start_line / end_line)
- Component type correctness
- parent_name populated for methods
- is_exported flag accuracy
- MODULE fallback for non-Python/JS files
- Empty content returns no components
"""

import pytest
from backend.app.models.domain import ComponentType
from backend.app.services.structure.extractor import (
    StructureExtractor,
    extract_directory_records,
)

FILE_ID = "file_test_001"
REPO_ID = "repo_test_001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract(path: str, content: str):
    return StructureExtractor.extract_components(FILE_ID, REPO_ID, path, content)


def _by_name(components, name):
    return [c for c in components if c["name"] == name]


def _one(components, name):
    matches = _by_name(components, name)
    assert len(matches) == 1, f"Expected 1 component named {name!r}, got {len(matches)}: {[c['name'] for c in components]}"
    return matches[0]


# ===========================================================================
# 1. Python – basic function and class detection
# ===========================================================================

PYTHON_BASIC = """\
def standalone():
    pass


class MyClass:
    def __init__(self):
        pass

    def method_one(self, x):
        return x

    async def async_method(self):
        pass


def another_function(a, b):
    return a + b
"""


class TestPythonBasic:

    def setup_method(self):
        self.comps = _extract("module.py", PYTHON_BASIC)

    def test_finds_top_level_functions(self):
        names = {c["name"] for c in self.comps if c["type"] == ComponentType.FUNCTION}
        assert "standalone" in names
        assert "another_function" in names

    def test_does_not_classify_methods_as_functions(self):
        func_names = {c["name"] for c in self.comps if c["type"] == ComponentType.FUNCTION}
        assert "__init__" not in func_names
        assert "method_one" not in func_names

    def test_finds_class(self):
        cls = _one(self.comps, "MyClass")
        assert cls["type"] == ComponentType.CLASS

    def test_finds_methods_with_correct_type(self):
        init = _one(self.comps, "__init__")
        assert init["type"] == ComponentType.METHOD
        m1 = _one(self.comps, "method_one")
        assert m1["type"] == ComponentType.METHOD

    def test_finds_async_method(self):
        am = _one(self.comps, "async_method")
        assert am["type"] == ComponentType.METHOD

    def test_method_parent_name_set(self):
        init = _one(self.comps, "__init__")
        assert init["parent_name"] == "MyClass"
        m1 = _one(self.comps, "method_one")
        assert m1["parent_name"] == "MyClass"

    def test_top_level_function_has_no_parent(self):
        fn = _one(self.comps, "standalone")
        assert fn["parent_name"] is None

    def test_start_line_standalone(self):
        fn = _one(self.comps, "standalone")
        assert fn["start_line"] == 1

    def test_start_line_class(self):
        cls = _one(self.comps, "MyClass")
        assert cls["start_line"] == 5

    def test_start_line_method_one(self):
        m = _one(self.comps, "method_one")
        assert m["start_line"] == 9

    def test_end_line_greater_equal_start(self):
        for c in self.comps:
            assert c["end_line"] >= c["start_line"], f"{c['name']} end_line < start_line"

    def test_class_end_line_covers_body(self):
        cls = _one(self.comps, "MyClass")
        # Class body ends at line 13 (async_method ends there)
        assert cls["end_line"] >= 13

    def test_signature_contains_name(self):
        fn = _one(self.comps, "another_function")
        assert "another_function" in fn["signature"]

    def test_file_id_and_repo_id_on_every_component(self):
        for c in self.comps:
            assert c["file_id"] == FILE_ID
            assert c["repository_id"] == REPO_ID


# ===========================================================================
# 2. Python – __all__ export detection
# ===========================================================================

PYTHON_EXPORTS = """\
__all__ = ["public_func", "PublicClass"]


def public_func():
    pass


def _private_func():
    pass


class PublicClass:
    def method(self):
        pass


class _PrivateClass:
    pass
"""


class TestPythonExports:

    def setup_method(self):
        self.comps = _extract("exports.py", PYTHON_EXPORTS)

    def test_public_func_is_exported(self):
        fn = _one(self.comps, "public_func")
        assert fn["is_exported"] is True

    def test_public_class_is_exported(self):
        cls = _one(self.comps, "PublicClass")
        assert cls["is_exported"] is True

    def test_private_func_not_exported(self):
        fn = _one(self.comps, "_private_func")
        assert fn["is_exported"] is False

    def test_private_class_not_exported(self):
        cls = _one(self.comps, "_PrivateClass")
        assert cls["is_exported"] is False

    def test_method_not_directly_exported(self):
        m = _one(self.comps, "method")
        assert m["is_exported"] is False


# ===========================================================================
# 3. Python – async top-level function
# ===========================================================================

PYTHON_ASYNC = """\
async def fetch_data(url: str):
    pass


async def process(items):
    pass
"""


class TestPythonAsync:

    def setup_method(self):
        self.comps = _extract("async_module.py", PYTHON_ASYNC)

    def test_async_functions_found(self):
        names = {c["name"] for c in self.comps}
        assert "fetch_data" in names
        assert "process" in names

    def test_async_functions_typed_as_function(self):
        fn = _one(self.comps, "fetch_data")
        assert fn["type"] == ComponentType.FUNCTION

    def test_async_function_start_line(self):
        fn = _one(self.comps, "fetch_data")
        assert fn["start_line"] == 1

    def test_async_function_signature_has_async(self):
        fn = _one(self.comps, "fetch_data")
        assert "async" in fn["signature"]


# ===========================================================================
# 4. Python – regex fallback (syntax error source)
# ===========================================================================

PYTHON_SYNTAX_ERROR = """\
class BrokenClass:
    def method_a(self):
        pass

def top_func():
    pass
"""

# Inject a deliberate SyntaxError by appending invalid Python
PYTHON_SYNTAX_ERROR_SOURCE = PYTHON_SYNTAX_ERROR + "\n!!invalid!!\n"


class TestPythonFallback:

    def setup_method(self):
        self.comps = _extract("broken.py", PYTHON_SYNTAX_ERROR_SOURCE)

    def test_class_found_via_fallback(self):
        classes = [c for c in self.comps if c["type"] == ComponentType.CLASS]
        assert any(c["name"] == "BrokenClass" for c in classes)

    def test_method_found_via_fallback(self):
        methods = [c for c in self.comps if c["type"] == ComponentType.METHOD]
        assert any(c["name"] == "method_a" for c in methods)

    def test_function_found_via_fallback(self):
        funcs = [c for c in self.comps if c["type"] == ComponentType.FUNCTION]
        assert any(c["name"] == "top_func" for c in funcs)


# ===========================================================================
# 5. Python – empty file
# ===========================================================================

class TestPythonEmpty:

    def test_empty_file_returns_no_components(self):
        assert _extract("empty.py", "") == []

    def test_whitespace_only_returns_no_components(self):
        assert _extract("blank.py", "   \n\n  ") == []


# ===========================================================================
# 6. Python – representative service file (demo fixture)
# ===========================================================================

PYTHON_SERVICE = '''\
"""Ingestion service for RepoScope."""

__all__ = ["IngestionService"]

import os
import hashlib


def _helper(path: str) -> str:
    return path.strip()


class IngestionService:
    """Discovers and stores files."""

    def __init__(self, root: str) -> None:
        self.root = root

    def ingest(self, conn):
        """Run ingestion pipeline."""
        return []

    @staticmethod
    def validate(path: str) -> bool:
        return os.path.isdir(path)
'''


class TestPythonServiceFixture:

    def setup_method(self):
        self.comps = _extract("ingestion_service.py", PYTHON_SERVICE)

    def test_expected_files_count(self):
        # class + 3 methods + 1 helper function = 5 components total
        assert len(self.comps) == 5

    def test_expected_component_names(self):
        names = {c["name"] for c in self.comps}
        assert names == {"IngestionService", "__init__", "ingest", "validate", "_helper"}

    def test_class_is_exported_via_all(self):
        cls = _one(self.comps, "IngestionService")
        assert cls["is_exported"] is True

    def test_helper_function_not_exported(self):
        fn = _one(self.comps, "_helper")
        assert fn["is_exported"] is False

    def test_methods_have_correct_parent(self):
        for name in ("__init__", "ingest", "validate"):
            m = _one(self.comps, name)
            assert m["parent_name"] == "IngestionService"

    def test_method_start_lines(self):
        init = _one(self.comps, "__init__")
        assert init["start_line"] == 16

        ingest = _one(self.comps, "ingest")
        assert ingest["start_line"] == 19

        validate = _one(self.comps, "validate")
        assert validate["start_line"] == 24

    def test_helper_start_line(self):
        fn = _one(self.comps, "_helper")
        assert fn["start_line"] == 9

    def test_class_start_line(self):
        cls = _one(self.comps, "IngestionService")
        assert cls["start_line"] == 13

    def test_class_end_line_covers_all_methods(self):
        cls = _one(self.comps, "IngestionService")
        validate = _one(self.comps, "validate")
        assert cls["end_line"] >= validate["end_line"]


# ===========================================================================
# 7. JS/TS – named functions and classes
# ===========================================================================

JS_BASIC = """\
export function greet(name) {
    return `Hello ${name}`;
}

function helper(x) {
    return x * 2;
}

export class ApiClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async get(path) {
        return fetch(this.baseUrl + path);
    }

    post(path, data) {
        return fetch(this.baseUrl + path, { method: 'POST', body: data });
    }
}
"""


class TestJSBasic:

    def setup_method(self):
        self.comps = _extract("api.js", JS_BASIC)

    def test_exported_function_found(self):
        fn = _one(self.comps, "greet")
        assert fn["type"] == ComponentType.FUNCTION

    def test_unexported_function_found(self):
        fn = _one(self.comps, "helper")
        assert fn["type"] == ComponentType.FUNCTION

    def test_class_found(self):
        cls = _one(self.comps, "ApiClient")
        assert cls["type"] == ComponentType.CLASS

    def test_exported_function_is_exported(self):
        fn = _one(self.comps, "greet")
        assert fn["is_exported"] is True

    def test_unexported_function_not_exported(self):
        fn = _one(self.comps, "helper")
        assert fn["is_exported"] is False

    def test_exported_class_is_exported(self):
        cls = _one(self.comps, "ApiClient")
        assert cls["is_exported"] is True

    def test_class_start_line(self):
        cls = _one(self.comps, "ApiClient")
        assert cls["start_line"] == 9  # actual line 9 in the fixture

    def test_function_start_line(self):
        fn = _one(self.comps, "greet")
        assert fn["start_line"] == 1

    def test_end_line_greater_equal_start(self):
        for c in self.comps:
            assert c["end_line"] >= c["start_line"]


# ===========================================================================
# 8. JS/TS – arrow functions and TypeScript class
# ===========================================================================

TS_ARROWS = """\
export const parseResponse = (data: unknown): string => {
    return JSON.stringify(data);
};

const internalUtil = (x: number) => x * 2;

export class DataStore {
    private items: string[] = [];

    add(item: string): void {
        this.items.push(item);
    }

    getAll(): string[] {
        return this.items;
    }
}

export { DataStore };
"""


class TestTSArrows:

    def setup_method(self):
        self.comps = _extract("store.ts", TS_ARROWS)

    def test_exported_arrow_found(self):
        fn = _one(self.comps, "parseResponse")
        assert fn["type"] == ComponentType.FUNCTION

    def test_exported_arrow_is_exported(self):
        fn = _one(self.comps, "parseResponse")
        assert fn["is_exported"] is True

    def test_internal_arrow_found(self):
        fn = _one(self.comps, "internalUtil")
        assert fn["type"] == ComponentType.FUNCTION

    def test_internal_arrow_not_exported(self):
        fn = _one(self.comps, "internalUtil")
        assert fn["is_exported"] is False

    def test_class_is_exported(self):
        cls = _one(self.comps, "DataStore")
        assert cls["is_exported"] is True

    def test_component_names_present(self):
        names = {c["name"] for c in self.comps}
        assert "parseResponse" in names
        assert "internalUtil" in names
        assert "DataStore" in names


# ===========================================================================
# 9. Module fallback for non-Python/JS files
# ===========================================================================

class TestModuleFallback:

    def test_sql_file_produces_module_record(self):
        content = "SELECT * FROM users WHERE id = ?;"
        comps = _extract("queries.sql", content)
        assert len(comps) == 1
        assert comps[0]["type"] == ComponentType.MODULE
        assert comps[0]["name"] == "queries.sql"

    def test_yaml_file_produces_module_record(self):
        content = "name: reposcope\nversion: 1.0\n"
        comps = _extract("config.yaml", content)
        assert len(comps) == 1
        assert comps[0]["type"] == ComponentType.MODULE

    def test_module_record_covers_full_file(self):
        lines = ["line1\n", "line2\n", "line3\n"]
        content = "".join(lines)
        comps = _extract("README.md", content)
        assert comps[0]["start_line"] == 1
        assert comps[0]["end_line"] == 3

    def test_module_record_has_file_path_signature(self):
        comps = _extract("docs/intro.md", "# Intro\n")
        assert "docs/intro.md" in comps[0]["signature"]


# ===========================================================================
# 10. Directory record extraction
# ===========================================================================

class TestDirectoryRecords:

    def test_single_file_no_subdirs(self):
        records = extract_directory_records(REPO_ID, ["README.md"])
        assert records == []

    def test_nested_file_produces_directory_records(self):
        records = extract_directory_records(REPO_ID, ["src/utils/helpers.py"])
        names = {r["name"] for r in records}
        assert "src" in names
        assert "utils" in names

    def test_no_duplicate_directories(self):
        paths = [
            "src/a.py",
            "src/b.py",
            "src/utils/c.py",
            "src/utils/d.py",
        ]
        records = extract_directory_records(REPO_ID, paths)
        dir_names = [r["name"] for r in records]
        # "src" and "utils" should appear exactly once each
        assert dir_names.count("src") == 1
        assert dir_names.count("utils") == 1

    def test_directory_type_is_directory(self):
        records = extract_directory_records(REPO_ID, ["app/main.py"])
        assert all(r["type"] == ComponentType.DIRECTORY for r in records)

    def test_directory_parent_name(self):
        records = extract_directory_records(REPO_ID, ["a/b/c.py"])
        by_name = {r["name"]: r for r in records}
        assert "a" in by_name
        assert "b" in by_name
        assert by_name["a"]["parent_name"] is None
        assert by_name["b"]["parent_name"] == "a"

    def test_directory_start_end_line(self):
        records = extract_directory_records(REPO_ID, ["src/main.py"])
        for r in records:
            assert r["start_line"] == 1
            assert r["end_line"] == 1

    def test_directory_repository_id(self):
        records = extract_directory_records(REPO_ID, ["src/main.py"])
        assert all(r["repository_id"] == REPO_ID for r in records)

    def test_directory_file_id_is_empty_string(self):
        records = extract_directory_records(REPO_ID, ["src/main.py"])
        assert all(r["file_id"] == "" for r in records)

    def test_multiple_top_level_dirs(self):
        paths = ["frontend/app.js", "backend/main.py", "docs/index.md"]
        records = extract_directory_records(REPO_ID, paths)
        top_level = {r["name"] for r in records if r["parent_name"] is None}
        assert top_level == {"frontend", "backend", "docs"}

    def test_empty_file_list_returns_empty(self):
        assert extract_directory_records(REPO_ID, []) == []


# ===========================================================================
# 11. Full pipeline: representative demo repository structure
# ===========================================================================

DEMO_REPO_FILES = {
    "backend/app/services/ingestion/ingestion_service.py": '''\
"""Ingestion service."""

__all__ = ["IngestionService"]


class IngestionService:
    """Discovers and stores files."""

    @staticmethod
    def ingest_repository(conn, repo_id: str, source_path: str):
        """Run ingestion pipeline."""
        return 0, 0, []
''',
    "backend/app/services/structure/extractor.py": '''\
"""Structure extractor."""


def extract_components(file_id, repo_id, path, content):
    """Extract components."""
    return []


class StructureExtractor:
    """Public API."""

    @classmethod
    def extract(cls, path, content):
        return extract_components("", "", path, content)
''',
    "frontend/src/App.tsx": '''\
import React from 'react';

export default function App() {
    return <div>Hello</div>;
}

export const VERSION = "1.0";
''',
}


class TestDemoRepoStructure:

    def _run(self, rel_path: str):
        content = DEMO_REPO_FILES[rel_path]
        return _extract(rel_path, content)

    # ---- ingestion_service.py ----

    def test_ingestion_service_file_components(self):
        comps = self._run("backend/app/services/ingestion/ingestion_service.py")
        names = {c["name"] for c in comps}
        assert "IngestionService" in names
        assert "ingest_repository" in names

    def test_ingestion_service_class_exported(self):
        comps = self._run("backend/app/services/ingestion/ingestion_service.py")
        cls = _one(comps, "IngestionService")
        assert cls["is_exported"] is True

    def test_ingest_repository_is_method(self):
        comps = self._run("backend/app/services/ingestion/ingestion_service.py")
        m = _one(comps, "ingest_repository")
        assert m["type"] == ComponentType.METHOD
        assert m["parent_name"] == "IngestionService"

    # ---- extractor.py ----

    def test_extractor_file_components(self):
        comps = self._run("backend/app/services/structure/extractor.py")
        names = {c["name"] for c in comps}
        assert "extract_components" in names
        assert "StructureExtractor" in names
        assert "extract" in names

    def test_extract_components_is_function(self):
        comps = self._run("backend/app/services/structure/extractor.py")
        fn = _one(comps, "extract_components")
        assert fn["type"] == ComponentType.FUNCTION

    def test_extract_is_method_of_structure_extractor(self):
        comps = self._run("backend/app/services/structure/extractor.py")
        m = _one(comps, "extract")
        assert m["type"] == ComponentType.METHOD
        assert m["parent_name"] == "StructureExtractor"

    # ---- App.tsx ----

    def test_app_tsx_components(self):
        comps = self._run("frontend/src/App.tsx")
        names = {c["name"] for c in comps}
        assert "App" in names

    def test_app_function_is_exported(self):
        comps = self._run("frontend/src/App.tsx")
        fn = _one(comps, "App")
        assert fn["is_exported"] is True

    # ---- Directories from demo paths ----

    def test_directory_records_for_demo_paths(self):
        records = extract_directory_records(REPO_ID, list(DEMO_REPO_FILES.keys()))
        dir_names = {r["name"] for r in records}
        assert "backend" in dir_names
        assert "app" in dir_names
        assert "services" in dir_names
        assert "ingestion" in dir_names
        assert "structure" in dir_names
        assert "frontend" in dir_names
        assert "src" in dir_names

    def test_no_file_names_in_directory_records(self):
        records = extract_directory_records(REPO_ID, list(DEMO_REPO_FILES.keys()))
        dir_names = {r["name"] for r in records}
        assert "ingestion_service.py" not in dir_names
        assert "extractor.py" not in dir_names
        assert "App.tsx" not in dir_names


# ===========================================================================
# 12. Regression: _find_block_end brace-free single-line arrows
# ===========================================================================

JS_BRACE_FREE_ARROWS = """\
const double = (x) => x * 2;
const triple = (x) => x * 3;
const square = (x) => x * x;
"""

JS_MIXED_ARROWS = """\
const add = (a, b) => a + b;

function greet(name) {
    return name;
}

const negate = (x) => -x;
"""


class TestBraceFreeArrow:
    """BUG: brace-free arrow functions got end_line = start_line + 1 due to
    depth=0 triggering early return in _find_block_end on the next brace-free line.

    After the fix, brace-free expressions fall through to the conservative
    ``min(start_idx + 50, total)`` estimate (file-end), which is preferable to
    the old behaviour of landing exactly on the *next* function's start line.
    """

    def test_brace_free_arrow_end_not_off_by_one(self):
        """The previous bug set end_line = start_line + 1, pointing exactly at
        the next function's start line.  After the fix the fallback uses file-end,
        so end_line must NOT equal ``start_line + 1`` when another arrow starts
        on that very next line."""
        comps = _extract("arrows.js", JS_BRACE_FREE_ARROWS)
        double = _one(comps, "double")
        triple = _one(comps, "triple")
        # Before the fix: double.end_line == 2 == triple.start_line (wrong).
        # After the fix: end_line is the file end (3), not triple's start (2).
        assert double["end_line"] != triple["start_line"], (
            f"double.end_line={double['end_line']} must not equal "
            f"triple.start_line={triple['start_line']} (off-by-one regression)"
        )

    def test_brace_free_arrow_end_gte_start(self):
        comps = _extract("arrows.js", JS_BRACE_FREE_ARROWS)
        for c in comps:
            assert c["end_line"] >= c["start_line"]

    def test_mixed_braced_and_brace_free_start_lines(self):
        """Start-line accuracy is unaffected by the end_line fix."""
        comps = _extract("mixed.js", JS_MIXED_ARROWS)
        add = _one(comps, "add")
        greet = _one(comps, "greet")
        negate = _one(comps, "negate")
        assert add["start_line"] == 1
        assert greet["start_line"] == 3
        assert negate["start_line"] == 7

    def test_end_line_always_gte_start(self):
        comps = _extract("arrows.js", JS_BRACE_FREE_ARROWS)
        for c in comps:
            assert c["end_line"] >= c["start_line"]


# ===========================================================================
# 13. Regression: _JS_METHOD matches JS keywords (catch, finally) as methods
# ===========================================================================

JS_WITH_CATCH = """\
export class Service {
    process(data) {
        try {
            return data.trim();
        }
        catch(err) {
            console.error(err);
        }
    }

    validate(input) {
        return Boolean(input);
    }
}
"""

JS_WITH_FINALLY = """\
class Resource {
    open() {
        try {
            this.handle = acquire();
        } finally {
            cleanup();
        }
    }
}
"""


class TestJSKeywordNotMethod:
    """BUG: 'catch' and 'finally' were not in the _JS_METHOD skip-list, causing them
    to be recorded as phantom class methods when they appeared on their own line."""

    def test_catch_not_emitted_as_method(self):
        comps = _extract("service.js", JS_WITH_CATCH)
        names = {c["name"] for c in comps if c["type"] == ComponentType.METHOD}
        assert "catch" not in names, f"'catch' should not appear as a method; methods={names}"

    def test_catch_block_does_not_produce_extra_component(self):
        comps = _extract("service.js", JS_WITH_CATCH)
        # Only expected methods: process, validate
        method_names = {c["name"] for c in comps if c["type"] == ComponentType.METHOD}
        assert method_names == {"process", "validate"}, f"Unexpected methods: {method_names}"

    def test_finally_not_emitted_as_method(self):
        comps = _extract("resource.js", JS_WITH_FINALLY)
        names = {c["name"] for c in comps if c["type"] == ComponentType.METHOD}
        assert "finally" not in names, f"'finally' should not appear as a method; methods={names}"
