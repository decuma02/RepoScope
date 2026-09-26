import ast
import re
import uuid
from typing import List, Dict, Any
from app.models.domain import ComponentType

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, file_id: str, repo_id: str, lines: List[str]):
        self.file_id = file_id
        self.repo_id = repo_id
        self.lines = lines
        self.components: List[Dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        end_line = getattr(node, 'end_lineno', node.lineno + len(node.body))
        docstring = ast.get_docstring(node) or f"Class {node.name}"
        self.components.append({
            "id": f"comp_{uuid.uuid4().hex[:12]}",
            "file_id": self.file_id,
            "repository_id": self.repo_id,
            "name": node.name,
            "type": ComponentType.CLASS,
            "start_line": node.lineno,
            "end_line": end_line,
            "signature": f"class {node.name}",
            "summary": docstring[:150]
        })
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._add_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._add_function(node, is_async=True)
        self.generic_visit(node)

    def _add_function(self, node: Any, is_async: bool = False):
        end_line = getattr(node, 'end_lineno', node.lineno + 10)
        docstring = ast.get_docstring(node) or f"Function {node.name}"
        args = [arg.arg for arg in node.args.args]
        sig_prefix = "async def" if is_async else "def"
        sig = f"{sig_prefix} {node.name}({', '.join(args)})"

        self.components.append({
            "id": f"comp_{uuid.uuid4().hex[:12]}",
            "file_id": self.file_id,
            "repository_id": self.repo_id,
            "name": node.name,
            "type": ComponentType.FUNCTION,
            "start_line": node.lineno,
            "end_line": end_line,
            "signature": sig,
            "summary": docstring[:150]
        })

class StructureExtractor:
    """
    AST & Regex-based code component structure extractor.
    Extracts functions, classes, modules, and endpoints with start/end line bounds.
    """

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

        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ""

        if ext == "py":
            components.extend(cls._extract_python_components_ast(file_id, repo_id, content, lines))
        elif ext in ["js", "ts", "jsx", "tsx"]:
            components.extend(cls._extract_js_ts_components(file_id, repo_id, lines, total_lines))
        else:
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
    def _extract_python_components_ast(cls, file_id: str, repo_id: str, content: str, lines: List[str]) -> List[Dict[str, Any]]:
        try:
            tree = ast.parse(content)
            visitor = PythonASTVisitor(file_id, repo_id, lines)
            visitor.visit(tree)
            return visitor.components
        except SyntaxError:
            # Fallback to regex line matching if Python file has syntax errors
            return cls._extract_python_fallback(file_id, repo_id, lines)

    @classmethod
    def _extract_python_fallback(cls, file_id: str, repo_id: str, lines: List[str]) -> List[Dict[str, Any]]:
        components = []
        py_def = re.compile(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
        py_class = re.compile(r"^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*")

        for idx, line in enumerate(lines, start=1):
            c_match = py_class.match(line)
            if c_match:
                components.append({
                    "id": f"comp_{uuid.uuid4().hex[:12]}",
                    "file_id": file_id,
                    "repository_id": repo_id,
                    "name": c_match.group(1),
                    "type": ComponentType.CLASS,
                    "start_line": idx,
                    "end_line": min(idx + 30, len(lines)),
                    "signature": line.strip(),
                    "summary": f"Class {c_match.group(1)}"
                })
            f_match = py_def.match(line)
            if f_match:
                components.append({
                    "id": f"comp_{uuid.uuid4().hex[:12]}",
                    "file_id": file_id,
                    "repository_id": repo_id,
                    "name": f_match.group(1),
                    "type": ComponentType.FUNCTION,
                    "start_line": idx,
                    "end_line": min(idx + 20, len(lines)),
                    "signature": line.strip(),
                    "summary": f"Function {f_match.group(1)}"
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
