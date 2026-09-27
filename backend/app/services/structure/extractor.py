"""
Structure Extractor
===================
Lightweight, AST-based (Python) and regex-based (JS/TS) code structure extractor.

Produces component records for:
  - directories     (type=DIRECTORY, one per unique parent directory in a file set)
  - files           (type=MODULE,    one per file when no finer-grained info is available)
  - classes         (type=CLASS)
  - functions       (type=FUNCTION,  top-level only)
  - methods         (type=METHOD,    functions nested directly inside a class)
  - exported symbols (is_exported=True when `__all__` / `export` keyword detected)

Each record carries:
  - id              unique component id
  - file_id         FK to files table
  - repository_id   FK to repositories table
  - name            symbol name
  - type            ComponentType enum value
  - start_line      1-based, inclusive
  - end_line        1-based, inclusive
  - signature       brief human-readable signature string
  - summary         one-line docstring / fallback
  - is_exported     True if symbol is explicitly exported
  - parent_name     name of the enclosing class (for methods)
"""

import ast
import re
import uuid
from typing import Any, Dict, List, Optional, Set

from backend.app.models.domain import ComponentType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return f"comp_{uuid.uuid4().hex[:12]}"


def _base(file_id: str, repo_id: str) -> Dict[str, Any]:
    return {
        "id": _new_id(),
        "file_id": file_id,
        "repository_id": repo_id,
        "is_exported": False,
        "parent_name": None,
    }


# ---------------------------------------------------------------------------
# Python AST visitor
# ---------------------------------------------------------------------------

class _PythonVisitor(ast.NodeVisitor):
    """Collects classes, methods, and top-level functions from a Python AST."""

    def __init__(self, file_id: str, repo_id: str) -> None:
        self.file_id = file_id
        self.repo_id = repo_id
        self.components: List[Dict[str, Any]] = []
        self._class_stack: List[str] = []  # track nesting

    # ---- Classes ----

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        end_line = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node) or f"Class {node.name}"
        rec = _base(self.file_id, self.repo_id)
        rec.update({
            "name": node.name,
            "type": ComponentType.CLASS,
            "start_line": node.lineno,
            "end_line": end_line,
            "signature": f"class {node.name}",
            "summary": docstring[:150],
        })
        self.components.append(rec)

        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    # ---- Functions / methods ----

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_function(node, is_async=False)
        # Do NOT call generic_visit here: we don't want nested functions inside
        # methods to produce extra records (keeps the output flat and useful).

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_function(node, is_async=True)

    def _add_function(self, node: Any, *, is_async: bool) -> None:
        end_line = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node) or ""

        args = [arg.arg for arg in node.args.args]
        prefix = "async def" if is_async else "def"
        sig = f"{prefix} {node.name}({', '.join(args)})"

        in_class = bool(self._class_stack)
        comp_type = ComponentType.METHOD if in_class else ComponentType.FUNCTION
        parent = self._class_stack[-1] if in_class else None
        summary = docstring[:150] if docstring else f"{'Method' if in_class else 'Function'} {node.name}"

        rec = _base(self.file_id, self.repo_id)
        rec.update({
            "name": node.name,
            "type": comp_type,
            "start_line": node.lineno,
            "end_line": end_line,
            "signature": sig,
            "summary": summary,
            "parent_name": parent,
        })
        self.components.append(rec)
        # Intentionally do NOT recurse so nested closures/lambdas are ignored.


def _python_all_exports(tree: ast.Module) -> Set[str]:
    """Return names listed in module-level __all__ = [...], or empty set."""
    exports: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            exports.add(elt.value)
    return exports


def _extract_python(file_id: str, repo_id: str, content: str) -> List[Dict[str, Any]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _extract_python_fallback(file_id, repo_id, content.splitlines())

    exports = _python_all_exports(tree)

    visitor = _PythonVisitor(file_id, repo_id)
    visitor.visit(tree)

    for comp in visitor.components:
        if comp["name"] in exports:
            comp["is_exported"] = True

    return visitor.components


def _extract_python_fallback(file_id: str, repo_id: str, lines: List[str]) -> List[Dict[str, Any]]:
    """Regex fallback for files that fail AST parsing."""
    components: List[Dict[str, Any]] = []
    py_def = re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
    py_class = re.compile(r"^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\b")

    # Track current class for method detection (simple indent heuristic)
    current_class: Optional[str] = None
    current_class_indent: int = -1

    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Leave class scope when indentation drops back
        if current_class is not None and stripped and indent <= current_class_indent:
            current_class = None
            current_class_indent = -1

        c_match = py_class.match(line)
        if c_match:
            current_class = c_match.group(1)
            current_class_indent = indent
            rec = _base(file_id, repo_id)
            rec.update({
                "name": current_class,
                "type": ComponentType.CLASS,
                "start_line": idx,
                "end_line": min(idx + 30, len(lines)),
                "signature": line.strip(),
                "summary": f"Class {current_class}",
            })
            components.append(rec)
            continue

        f_match = py_def.match(line)
        if f_match:
            name = f_match.group(1)
            in_class = current_class is not None and indent > current_class_indent
            rec = _base(file_id, repo_id)
            rec.update({
                "name": name,
                "type": ComponentType.METHOD if in_class else ComponentType.FUNCTION,
                "start_line": idx,
                "end_line": min(idx + 20, len(lines)),
                "signature": line.strip(),
                "summary": f"{'Method' if in_class else 'Function'} {name}",
                "parent_name": current_class if in_class else None,
            })
            components.append(rec)

    return components


# ---------------------------------------------------------------------------
# JS / TS extractor (regex-based)
# ---------------------------------------------------------------------------

# Horizontal whitespace only (spaces/tabs, no newlines)
_HS = r"[^\S\n]*"

# Named function declarations: [export] [default] [async] function Foo(
_JS_NAMED_FUNC = re.compile(
    r"^" + _HS + r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?P<name>[a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(",
    re.MULTILINE,
)
# Arrow / const functions: [export] const Foo = [async] (...[: ReturnType]) =>
_JS_ARROW_FUNC = re.compile(
    r"^" + _HS + r"(?:export\s+)?(?:const|let|var)\s+(?P<name>[a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)(?:[^\S\n]*:[^\S\n]*\S+)?\s*=>",
    re.MULTILINE,
)
# Class declarations: [export] [default] class Foo
_JS_CLASS = re.compile(
    r"^" + _HS + r"(?P<export>export\s+)?(?:default\s+)?class\s+(?P<name>[a-zA-Z_$][a-zA-Z0-9_$]*)",
    re.MULTILINE,
)
# Class method: indented method name( — NOT prefixed with function keyword
_JS_METHOD = re.compile(
    r"^[^\S\n]+(?:async\s+)?(?:static\s+)?(?:get\s+|set\s+)?(?P<name>[a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
# export { ... } named re-exports
_JS_EXPORT_BRACE = re.compile(r"^\s*export\s*\{([^}]+)\}", re.MULTILINE)
# export default Identifier
_JS_EXPORT_DEFAULT = re.compile(r"^\s*export\s+default\s+([a-zA-Z_$][a-zA-Z0-9_$]*)", re.MULTILINE)


def _js_collect_exports(content: str) -> Set[str]:
    """Return names that are directly exported in JS/TS source."""
    exports: Set[str] = set()

    # export { Foo, Bar as Baz }
    for m in _JS_EXPORT_BRACE.finditer(content):
        for part in m.group(1).split(","):
            token = part.strip().split()[0]  # "Foo" or "Foo as Bar" → "Foo"
            if token:
                exports.add(token)

    # export default Identifier
    for m in _JS_EXPORT_DEFAULT.finditer(content):
        exports.add(m.group(1))

    # export function/class/const — pick names from inline declarations
    for m in re.finditer(
        r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)",
        content, re.MULTILINE
    ):
        exports.add(m.group(1))

    return exports


def _line_of(content: str, match_start: int) -> int:
    """Return the 1-based line number for a regex match start position."""
    return content.count("\n", 0, match_start) + 1


def _extract_js_ts(file_id: str, repo_id: str, lines: List[str]) -> List[Dict[str, Any]]:
    content = "\n".join(lines)
    total = len(lines)
    exported_names = _js_collect_exports(content)
    components: List[Dict[str, Any]] = []

    # Build line-indexed position map for class boundary estimation.
    class_end: Dict[int, int] = {}  # start_line -> end_line

    # Pass 1: classes
    for m in _JS_CLASS.finditer(content):
        start_line = _line_of(content, m.start())
        name = m.group("name")
        is_exp = bool(m.group("export")) or (name in exported_names)
        # Estimate end by scanning forward for matching brace
        end_line = _find_block_end(lines, start_line - 1, total)
        class_end[start_line] = end_line

        rec = _base(file_id, repo_id)
        rec.update({
            "name": name,
            "type": ComponentType.CLASS,
            "start_line": start_line,
            "end_line": end_line,
            "signature": lines[start_line - 1].strip(),
            "summary": f"JS/TS class {name}",
            "is_exported": is_exp,
        })
        components.append(rec)

    # Pass 2: named functions and arrow functions
    for pattern in (_JS_NAMED_FUNC, _JS_ARROW_FUNC):
        for m in pattern.finditer(content):
            start_line = _line_of(content, m.start())
            name = m.group("name")
            is_exp = name in exported_names or "export" in lines[start_line - 1]
            end_line = _find_block_end(lines, start_line - 1, total)

            # Determine if inside a class (method)
            parent = _enclosing_class(start_line, class_end, components)
            comp_type = ComponentType.METHOD if parent else ComponentType.FUNCTION

            rec = _base(file_id, repo_id)
            rec.update({
                "name": name,
                "type": comp_type,
                "start_line": start_line,
                "end_line": end_line,
                "signature": lines[start_line - 1].strip(),
                "summary": f"JS/TS {'method' if parent else 'function'} {name}",
                "is_exported": is_exp,
                "parent_name": parent,
            })
            components.append(rec)

    # Pass 3: class methods (indented non-function methods not caught above)
    for m in _JS_METHOD.finditer(content):
        name = m.group("name")
        # Skip constructor and JS control-flow keywords that happen to match the
        # method pattern (e.g. `catch(err) {`, `finally {` on its own line).
        if name in (
            "if", "for", "while", "switch", "constructor",
            "catch", "finally", "do", "else",
            "new", "return", "delete", "typeof", "instanceof", "void",
        ):
            continue
        start_line = _line_of(content, m.start())

        # Only record as method if clearly inside a class block
        parent = _enclosing_class(start_line, class_end, components)
        if not parent:
            continue
        # Avoid duplicates from pass 2
        if any(c["name"] == name and c["start_line"] == start_line for c in components):
            continue

        end_line = _find_block_end(lines, start_line - 1, total)
        rec = _base(file_id, repo_id)
        rec.update({
            "name": name,
            "type": ComponentType.METHOD,
            "start_line": start_line,
            "end_line": end_line,
            "signature": lines[start_line - 1].strip(),
            "summary": f"JS/TS method {name}",
            "parent_name": parent,
        })
        components.append(rec)

    return components


def _find_block_end(lines: List[str], start_idx: int, total: int) -> int:
    """
    Scan forward from *start_idx* counting braces to find the closing ``}``.
    Returns 1-based line number of the closing brace, or a conservative estimate.

    The depth check fires only after we have entered a block (seen at least one
    ``{``).  Without this guard, brace-free single-line expressions such as
    ``const fn = (x) => x * 2`` would get an end_line that bleeds into the
    following line because depth stays 0 from the start.
    """
    depth = 0
    entered_block = False
    for i in range(start_idx, total):
        opens = lines[i].count("{")
        closes = lines[i].count("}")
        depth += opens - closes
        if opens:
            entered_block = True
        if entered_block and depth <= 0:
            return i + 1
    return min(start_idx + 50, total)


def _enclosing_class(
    line: int,
    class_end: Dict[int, int],
    components: List[Dict[str, Any]],
) -> Optional[str]:
    """Return the name of the innermost class whose line range contains *line*."""
    best: Optional[str] = None
    best_start = -1
    for comp in components:
        if comp["type"] == ComponentType.CLASS:
            s, e = comp["start_line"], comp["end_line"]
            if s < line <= e and s > best_start:
                best = comp["name"]
                best_start = s
    return best


# ---------------------------------------------------------------------------
# Directory record builder
# ---------------------------------------------------------------------------

def extract_directory_records(
    repo_id: str,
    file_paths: List[str],
) -> List[Dict[str, Any]]:
    """
    Build one DIRECTORY component record per unique directory path found
    in *file_paths* (forward-slash relative paths).

    Directory records use file_id="" (no associated file) and line range 1–1.
    """
    seen: Set[str] = set()
    records: List[Dict[str, Any]] = []

    for fp in file_paths:
        parts = fp.split("/")
        # All ancestor directories (not the file itself)
        for depth in range(1, len(parts)):
            dir_path = "/".join(parts[:depth])
            if dir_path in seen:
                continue
            seen.add(dir_path)
            name = parts[depth - 1]
            parent = "/".join(parts[: depth - 1]) if depth > 1 else None
            rec = {
                "id": _new_id(),
                "file_id": "",          # directory records have no single file owner
                "repository_id": repo_id,
                "name": name,
                "type": ComponentType.DIRECTORY,
                "start_line": 1,
                "end_line": 1,
                "signature": f"dir:{dir_path}",
                "summary": f"Directory {dir_path}",
                "is_exported": False,
                "parent_name": parent,
            }
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class StructureExtractor:
    """
    AST & regex-based code component structure extractor.

    Extracts functions, methods, classes, and modules with start/end line
    bounds, export status, and parent name.

    Supports Python (AST + fallback) and JS/TS (regex).
    Other extensions produce a single MODULE record for the file.
    """

    @classmethod
    def extract_components(
        cls,
        file_id: str,
        repo_id: str,
        file_path: str,
        content: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract structure components from a single source file.

        Returns a list of component dicts, each containing:
          id, file_id, repository_id, name, type, start_line, end_line,
          signature, summary, is_exported, parent_name.
        """
        components: List[Dict[str, Any]] = []
        lines = content.splitlines()
        total_lines = len(lines)

        if not content.strip():
            return components

        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

        if ext == "py":
            components.extend(_extract_python(file_id, repo_id, content))
        elif ext in ("js", "ts", "jsx", "tsx", "mjs", "cjs"):
            components.extend(_extract_js_ts(file_id, repo_id, lines))
        else:
            # Generic fallback: represent the file as a MODULE record
            components.append({
                "id": _new_id(),
                "file_id": file_id,
                "repository_id": repo_id,
                "name": file_path.split("/")[-1],
                "type": ComponentType.MODULE,
                "start_line": 1,
                "end_line": max(1, total_lines),
                "signature": f"file:{file_path}",
                "summary": "Source file",
                "is_exported": False,
                "parent_name": None,
            })

        return components
