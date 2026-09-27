"""
Relationship Extractor
======================
Deterministic, AST/regex-based extractor for IMPORTS and EXPORTS relationships.

For every source file the extractor produces:

  IMPORTS relationships
  ---------------------
  One record per imported module/symbol, keyed by the import statement location.
  Relative imports are resolved to absolute repo paths where possible.
  Unresolved imports still produce a record with ``target_resolved=False``.

  EXPORTS relationships
  ---------------------
  One record per exported symbol detected in the file (``__all__`` for Python,
  ``export`` keyword for JS/TS).  The target is the component within the same
  file that bears the exported name.

Determinism guarantee
---------------------
IDs are SHA-1 digests of ``(repo_id, source_file_path, rel_type, target_spec,
source_line)`` so the same repository always produces the same record set
regardless of traversal order or Python dict insertion order.  The returned
list is sorted by ``(source_file, source_line, rel_type, target_spec)``.
"""

from __future__ import annotations

import ast
import hashlib
import posixpath
import re
from typing import Any, Dict, List, Optional, Set

from backend.app.models.domain import RelationshipType


# ---------------------------------------------------------------------------
# Stable ID helper
# ---------------------------------------------------------------------------

def _rel_id(repo_id: str, source_path: str, rel_type: str, target_spec: str, line: int) -> str:
    key = f"{repo_id}\x00{source_path}\x00{rel_type}\x00{target_spec}\x00{line}"
    return "rel_" + hashlib.sha1(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Python import AST extraction
# ---------------------------------------------------------------------------

def _python_imports(content: str) -> List[Dict[str, Any]]:
    """
    Return list of dicts with keys:
      module, names (list[str]), source_line, is_relative (bool), level (int)

    Uses the AST so multi-line imports and parenthesised imports are handled
    correctly.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _python_imports_fallback(content)

    results: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append({
                    "module": alias.name,
                    "names": [alias.asname or alias.name.split(".")[-1]],
                    "source_line": node.lineno,
                    "is_relative": False,
                    "level": 0,
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            results.append({
                "module": module,
                "names": names,
                "source_line": node.lineno,
                "is_relative": node.level > 0,
                "level": node.level,
            })
    # Sort by line so output order is deterministic
    results.sort(key=lambda r: r["source_line"])
    return results


_PY_FROM_RE = re.compile(
    r"^(\s*)from\s+(\.*)([a-zA-Z0-9_\.]*)\s+import\s+([^\n]+)", re.MULTILINE
)
_PY_IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)


def _python_imports_fallback(content: str) -> List[Dict[str, Any]]:
    """Regex fallback used when AST parsing fails."""
    results: List[Dict[str, Any]] = []
    lines = content.splitlines()
    for line_no, line in enumerate(lines, start=1):
        m = _PY_FROM_RE.match(line)
        if m:
            level = len(m.group(2))
            module = m.group(3)
            names_raw = m.group(4).strip().rstrip("\\").strip()
            names = [n.strip() for n in names_raw.split(",") if n.strip()]
            results.append({
                "module": module,
                "names": names,
                "source_line": line_no,
                "is_relative": level > 0,
                "level": level,
            })
            continue
        m2 = _PY_IMPORT_RE.match(line)
        if m2:
            results.append({
                "module": m2.group(1),
                "names": [m2.group(1).split(".")[-1]],
                "source_line": line_no,
                "is_relative": False,
                "level": 0,
            })
    results.sort(key=lambda r: r["source_line"])
    return results


# ---------------------------------------------------------------------------
# Python export extraction
# ---------------------------------------------------------------------------

def _python_exports(content: str) -> List[Dict[str, Any]]:
    """
    Return list of dicts: {name, source_line}
    Covers only __all__ = [...] at module level (AST-based).
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    results: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            results.append({
                                "name": elt.value,
                                "source_line": node.lineno,
                            })
    results.sort(key=lambda r: (r["source_line"], r["name"]))
    return results


# ---------------------------------------------------------------------------
# JS/TS import & export extraction
# ---------------------------------------------------------------------------

_JS_IMPORT_RE = re.compile(
    r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_JS_REQUIRE_RE = re.compile(
    r"""^\s*(?:const|let|var)\s+\S.*?=\s*require\(['"]([^'"]+)['"]\)""",
    re.MULTILINE,
)
# NOTE: use [^\S\n]* (horizontal whitespace only) not \s* so patterns never
# cross a newline boundary — otherwise ^ (MULTILINE) can anchor to the end of
# the previous line when a blank line precedes the export keyword.
_JS_EXPORT_NAMED_RE = re.compile(
    r"""^[^\S\n]*export\s+(?:(?:async\s+)?function\*?\s+|class\s+|const\s+|let\s+|var\s+)([a-zA-Z_$][a-zA-Z0-9_$]*)""",
    re.MULTILINE,
)
_JS_EXPORT_BRACE_RE = re.compile(r"""^[^\S\n]*export\s*\{([^}]+)\}""", re.MULTILINE)
_JS_EXPORT_DEFAULT_RE = re.compile(
    r"""^[^\S\n]*export\s+default\s+(?:(?:async\s+)?(?:function\*?|class)\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)""",
    re.MULTILINE,
)


def _js_imports(content: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: Set[tuple] = set()
    lines = content.splitlines()
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln) + 1)

    def _lineno(pos: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1  # 1-based

    for pat in (_JS_IMPORT_RE, _JS_REQUIRE_RE):
        for m in pat.finditer(content):
            spec = m.group(1)
            line = _lineno(m.start())
            key = (spec, line)
            if key not in seen:
                seen.add(key)
                results.append({"module": spec, "source_line": line})
    results.sort(key=lambda r: r["source_line"])
    return results


def _js_exports(content: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: Set[tuple] = set()
    lines = content.splitlines()
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln) + 1)

    def _lineno(pos: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for m in _JS_EXPORT_NAMED_RE.finditer(content):
        name = m.group(1)
        line = _lineno(m.start())
        key = (name, line)
        if key not in seen:
            seen.add(key)
            results.append({"name": name, "source_line": line})
    for m in _JS_EXPORT_BRACE_RE.finditer(content):
        line = _lineno(m.start())
        for raw in m.group(1).split(","):
            name = raw.split(" as ")[0].strip()
            if name:
                key = (name, line)
                if key not in seen:
                    seen.add(key)
                    results.append({"name": name, "source_line": line})
    for m in _JS_EXPORT_DEFAULT_RE.finditer(content):
        name = m.group(1)
        line = _lineno(m.start())
        key = (name, line)
        if key not in seen:
            seen.add(key)
            results.append({"name": name, "source_line": line})
    results.sort(key=lambda r: (r["source_line"], r["name"]))
    return results


# ---------------------------------------------------------------------------
# Import resolver
# ---------------------------------------------------------------------------

def _resolve_python_import(
    module: str, current_path: str, path_map: Dict[str, str], level: int = 0
) -> Optional[str]:
    """Return file_id for a Python import, or None if unresolvable."""
    if not module and level == 0:
        return None

    if level > 0:
        # Relative import: climb `level` directories from current_path
        parts = current_path.replace("\\", "/").split("/")
        anchor_parts = parts[:-level] if level <= len(parts) - 1 else []
        if module:
            candidate_parts = anchor_parts + module.split(".")
        else:
            candidate_parts = anchor_parts
        candidate_file = "/".join(candidate_parts) + ".py"
        candidate_pkg = "/".join(candidate_parts) + "/__init__.py"
    else:
        parts = module.split(".")
        candidate_file = "/".join(parts) + ".py"
        candidate_pkg = "/".join(parts) + "/__init__.py"

    for rel_path, file_id in path_map.items():
        rp = rel_path.replace("\\", "/")
        if rp == candidate_file or rp.endswith("/" + candidate_file):
            return file_id
        if rp == candidate_pkg or rp.endswith("/" + candidate_pkg):
            return file_id
    return None


def _resolve_js_import(specifier: str, current_path: str, path_map: Dict[str, str]) -> Optional[str]:
    """Return file_id for a JS/TS relative import, or None if unresolvable."""
    if not specifier.startswith("."):
        return None

    current_dir = posixpath.dirname(current_path.replace("\\", "/"))
    # posixpath.normpath handles ../ correctly
    resolved = posixpath.normpath(posixpath.join(current_dir, specifier))

    candidates = [
        resolved,
        resolved + ".ts",
        resolved + ".tsx",
        resolved + ".js",
        resolved + ".jsx",
        resolved + "/index.ts",
        resolved + "/index.tsx",
        resolved + "/index.js",
    ]
    for cand in candidates:
        for rel_path, file_id in path_map.items():
            rp = rel_path.replace("\\", "/")
            if rp == cand or rp.lstrip("/") == cand.lstrip("/"):
                return file_id
    return None


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------

class RelationshipExtractor:
    """
    Extracts deterministic IMPORTS and EXPORTS relationship edges.

    Each relationship record contains:
      id              Stable SHA-1-based string ID
      repository_id
      source_file     Relative path of the file containing the relationship
      source_line     1-based line number of the statement
      type            RelationshipType.IMPORTS or RelationshipType.EXPORTS
      target_spec     Raw import specifier or exported symbol name
      target_file     Resolved relative path of the target file (or None)
      target_resolved True when the target file was found in the repository
    """

    @classmethod
    def extract_relationships(
        cls,
        repo_id: str,
        files_map: Dict[str, Dict[str, Any]],       # file_id -> file_dict
        components_by_file: Dict[str, List[Dict[str, Any]]],  # file_id -> components
        file_contents: Dict[str, str],              # file_id -> content
    ) -> List[Dict[str, Any]]:
        """Return a deterministic, sorted list of relationship records."""

        # Build a normalised relative-path → file_id lookup
        rel_to_id: Dict[str, str] = {}
        for file_id, info in files_map.items():
            rp = (info.get("relative_path") or info.get("path") or "").replace("\\", "/")
            if rp:
                rel_to_id[rp] = file_id

        id_to_rel: Dict[str, str] = {v: k for k, v in rel_to_id.items()}

        relationships: List[Dict[str, Any]] = []

        for file_id, file_info in sorted(files_map.items()):  # sorted for determinism
            content = file_contents.get(file_id, "")
            rel_path = (file_info.get("relative_path") or file_info.get("path") or "").replace("\\", "/")
            ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""

            # ----------------------------------------------------------
            # IMPORTS
            # ----------------------------------------------------------
            if ext == "py":
                for imp in _python_imports(content):
                    # For "from .. import service" module="" names=["service"].
                    # Use names[0] as the module fragment in that case so the
                    # resolver can locate the target file.
                    module = imp["module"]
                    level = imp["level"]
                    if not module and imp["names"]:
                        module = imp["names"][0]
                    target_id = _resolve_python_import(module, rel_path, rel_to_id, level)
                    target_rel = id_to_rel.get(target_id) if target_id else None
                    # target_spec identifies the target module, not what's imported from it.
                    dots = "." * level
                    target_spec = (dots + module).rstrip(".") or "."
                    relationships.append(cls._make(
                        repo_id=repo_id,
                        rel_type=RelationshipType.IMPORTS,
                        source_file=rel_path,
                        source_line=imp["source_line"],
                        target_spec=target_spec,
                        target_file=target_rel,
                        target_resolved=target_id is not None,
                    ))

            elif ext in ("js", "ts", "jsx", "tsx", "mjs", "cjs"):
                for imp in _js_imports(content):
                    target_id = _resolve_js_import(imp["module"], rel_path, rel_to_id)
                    target_rel = id_to_rel.get(target_id) if target_id else None
                    relationships.append(cls._make(
                        repo_id=repo_id,
                        rel_type=RelationshipType.IMPORTS,
                        source_file=rel_path,
                        source_line=imp["source_line"],
                        target_spec=imp["module"],
                        target_file=target_rel,
                        target_resolved=target_id is not None,
                    ))

            # ----------------------------------------------------------
            # EXPORTS
            # ----------------------------------------------------------
            if ext == "py":
                for exp in _python_exports(content):
                    relationships.append(cls._make(
                        repo_id=repo_id,
                        rel_type=RelationshipType.EXPORTS,
                        source_file=rel_path,
                        source_line=exp["source_line"],
                        target_spec=exp["name"],
                        target_file=rel_path,
                        target_resolved=True,
                    ))

            elif ext in ("js", "ts", "jsx", "tsx", "mjs", "cjs"):
                for exp in _js_exports(content):
                    relationships.append(cls._make(
                        repo_id=repo_id,
                        rel_type=RelationshipType.EXPORTS,
                        source_file=rel_path,
                        source_line=exp["source_line"],
                        target_spec=exp["name"],
                        target_file=rel_path,
                        target_resolved=True,
                    ))

        # Sort for fully deterministic output
        relationships.sort(key=lambda r: (
            r["source_file"], r["source_line"], r["type"], r["target_spec"]
        ))
        return relationships

    @staticmethod
    def _make(
        *,
        repo_id: str,
        rel_type: RelationshipType,
        source_file: str,
        source_line: int,
        target_spec: str,
        target_file: Optional[str],
        target_resolved: bool,
    ) -> Dict[str, Any]:
        return {
            "id": _rel_id(repo_id, source_file, rel_type.value, target_spec, source_line),
            "repository_id": repo_id,
            "type": rel_type,
            "source_file": source_file,
            "source_line": source_line,
            "target_spec": target_spec,
            "target_file": target_file,
            "target_resolved": target_resolved,
        }
