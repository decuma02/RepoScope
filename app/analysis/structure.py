import re
import uuid
from typing import List, Dict, Any
from app.models.domain import ComponentType

class StructureExtractor:
    """
    Lightweight AST & Regex-based code component structure extractor.
    Extracts functions, classes, modules, and endpoints with start/end line bounds.
    """

    PYTHON_DEF_PATTERN = re.compile(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)", re.MULTILINE)
    PYTHON_CLASS_PATTERN = re.compile(r"^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(\(.*?\))?", re.MULTILINE)

    JS_FUNC_PATTERN = re.compile(r"^\s*(?:async\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", re.MULTILINE)
    JS_CONST_FUNC_PATTERN = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", re.MULTILINE)
    JS_CLASS_PATTERN = re.compile(r"^\s*(?:export\s+)?class\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE)

    @classmethod
    def extract_components(cls, file_id: str, repo_id: str, file_path: str, content: str) -> List[Dict[str, Any]]:
        components = []
        lines = content.splitlines()
        total_lines = len(lines)

        if not content.strip():
            return components

        # Determine language
        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ""

        if ext == "py":
            components.extend(cls._extract_python_components(file_id, repo_id, lines, total_lines))
        elif ext in ["js", "ts", "jsx", "tsx"]:
            components.extend(cls._extract_js_ts_components(file_id, repo_id, lines, total_lines))
        else:
            # Fallback module component for generic files
            components.append({
                "id": f"comp_{uuid.uuid4().hex[:12]}",
                "file_id": file_id,
                "repository_id": repo_id,
                "name": file_path.split('/')[-1],
                "type": ComponentType.MODULE,
                "start_line": 1,
                "end_line": max(1, total_lines),
                "signature": f"file:{file_path}",
                "summary": "Source File"
            })

        return components

    @classmethod
    def _extract_python_components(cls, file_id: str, repo_id: str, lines: List[str], total_lines: int) -> List[Dict[str, Any]]:
        components = []
        for idx, line in enumerate(lines, start=1):
            class_match = cls.PYTHON_CLASS_PATTERN.match(line)
            if class_match:
                name = class_match.group(1)
                end = cls._estimate_block_end(lines, idx - 1)
                components.append({
                    "id": f"comp_{uuid.uuid4().hex[:12]}",
                    "file_id": file_id,
                    "repository_id": repo_id,
                    "name": name,
                    "type": ComponentType.CLASS,
                    "start_line": idx,
                    "end_line": end,
                    "signature": line.strip(),
                    "summary": f"Class {name}"
                })
                continue

            def_match = cls.PYTHON_DEF_PATTERN.match(line)
            if def_match:
                name = def_match.group(1)
                end = cls._estimate_block_end(lines, idx - 1)
                components.append({
                    "id": f"comp_{uuid.uuid4().hex[:12]}",
                    "file_id": file_id,
                    "repository_id": repo_id,
                    "name": name,
                    "type": ComponentType.FUNCTION,
                    "start_line": idx,
                    "end_line": end,
                    "signature": line.strip(),
                    "summary": f"Function {name}"
                })

        return components

    @classmethod
    def _extract_js_ts_components(cls, file_id: str, repo_id: str, lines: List[str], total_lines: int) -> List[Dict[str, Any]]:
        components = []
        for idx, line in enumerate(lines, start=1):
            class_match = cls.JS_CLASS_PATTERN.match(line)
            if class_match:
                name = class_match.group(1)
                components.append({
                    "id": f"comp_{uuid.uuid4().hex[:12]}",
                    "file_id": file_id,
                    "repository_id": repo_id,
                    "name": name,
                    "type": ComponentType.CLASS,
                    "start_line": idx,
                    "end_line": min(idx + 30, total_lines),
                    "signature": line.strip(),
                    "summary": f"JS/TS Class {name}"
                })
                continue

            func_match = cls.JS_FUNC_PATTERN.match(line) or cls.JS_CONST_FUNC_PATTERN.match(line)
            if func_match:
                name = func_match.group(1)
                components.append({
                    "id": f"comp_{uuid.uuid4().hex[:12]}",
                    "file_id": file_id,
                    "repository_id": repo_id,
                    "name": name,
                    "type": ComponentType.FUNCTION,
                    "start_line": idx,
                    "end_line": min(idx + 25, total_lines),
                    "signature": line.strip(),
                    "summary": f"JS/TS Function {name}"
                })

        return components

    @staticmethod
    def _estimate_block_end(lines: List[str], start_idx: int) -> int:
        if start_idx >= len(lines):
            return start_idx + 1
        start_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if not line.strip():
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= start_indent:
                return i
        return len(lines)
