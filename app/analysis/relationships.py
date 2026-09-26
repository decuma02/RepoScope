import re
import uuid
from typing import List, Dict, Any
from app.models.domain import RelationshipType

class RelationshipExtractor:
    """
    Extracts relationship edges (IMPORTS, EXPORTS, USES) between files and code components.
    """

    PYTHON_FROM_IMPORT_PATTERN = re.compile(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\s+([a-zA-Z0-9_\.,\s\*]+)", re.MULTILINE)
    PYTHON_DIRECT_IMPORT_PATTERN = re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)

    JS_IMPORT_PATTERN = re.compile(r"^\s*import\s+.*?from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
    JS_REQUIRE_PATTERN = re.compile(r"^\s*(?:const|let|var)\s+.*?=\s*require\(['\"]([^'\"]+)['\"]\)", re.MULTILINE)

    @classmethod
    def extract_relationships(
        cls,
        repo_id: str,
        files_map: Dict[str, Dict[str, Any]],  # file_id -> file_dict
        components_by_file: Dict[str, List[Dict[str, Any]]], # file_id -> components
        file_contents: Dict[str, str] # file_id -> content
    ) -> List[Dict[str, Any]]:
        relationships = []

        # Create path lookup helpers safely
        rel_path_to_file_id = {
            (info.get("relative_path") or info.get("path")): file_id 
            for file_id, info in files_map.items()
        }

        for file_id, file_info in files_map.items():
            content = file_contents.get(file_id, "")
            rel_path = file_info.get("relative_path") or file_info.get("path", "")

            lines = content.splitlines()
            for line_no, line in enumerate(lines, start=1):
                # Python From Imports (e.g. from app import user or from app.user import user_service)
                from_match = cls.PYTHON_FROM_IMPORT_PATTERN.search(line)
                if from_match:
                    pkg = from_match.group(1)
                    items = [i.strip() for i in from_match.group(2).split(',')]
                    for item in items:
                        target_file_id = cls._resolve_python_import(f"{pkg}.{item}", rel_path, rel_path_to_file_id) or \
                                         cls._resolve_python_import(pkg, rel_path, rel_path_to_file_id)
                        if target_file_id and target_file_id != file_id:
                            relationships.append({
                                "id": f"rel_{uuid.uuid4().hex[:12]}",
                                "repository_id": repo_id,
                                "source_type": "file",
                                "source_id": file_id,
                                "target_type": "file",
                                "target_id": target_file_id,
                                "type": RelationshipType.IMPORTS,
                                "confidence": 0.95,
                                "source_line": line_no,
                                "evidence": f"Import statement on line {line_no}: {line.strip()}"
                            })

                # Python Direct Imports (e.g. import app.user)
                direct_match = cls.PYTHON_DIRECT_IMPORT_PATTERN.search(line)
                if direct_match and not from_match:
                    mod = direct_match.group(1)
                    target_file_id = cls._resolve_python_import(mod, rel_path, rel_path_to_file_id)
                    if target_file_id and target_file_id != file_id:
                        relationships.append({
                            "id": f"rel_{uuid.uuid4().hex[:12]}",
                            "repository_id": repo_id,
                            "source_type": "file",
                            "source_id": file_id,
                            "target_type": "file",
                            "target_id": target_file_id,
                            "type": RelationshipType.IMPORTS,
                            "confidence": 0.95,
                            "source_line": line_no,
                            "evidence": f"Import statement on line {line_no}: {line.strip()}"
                        })

                # JS/TS Imports
                js_match = cls.JS_IMPORT_PATTERN.search(line) or cls.JS_REQUIRE_PATTERN.search(line)
                if js_match:
                    target_spec = js_match.group(1)
                    target_file_id = cls._resolve_js_import(target_spec, rel_path, rel_path_to_file_id)
                    if target_file_id and target_file_id != file_id:
                        relationships.append({
                            "id": f"rel_{uuid.uuid4().hex[:12]}",
                            "repository_id": repo_id,
                            "source_type": "file",
                            "source_id": file_id,
                            "target_type": "file",
                            "target_id": target_file_id,
                            "type": RelationshipType.IMPORTS,
                            "confidence": 0.95,
                            "source_line": line_no,
                            "evidence": f"Import/require on line {line_no}: {line.strip()}"
                        })

            # Approximate symbol USES matching
            for other_file_id, components in components_by_file.items():
                if other_file_id == file_id:
                    continue
                for comp in components:
                    comp_name = comp["name"]
                    if len(comp_name) >= 4 and comp_name in content:
                        relationships.append({
                            "id": f"rel_{uuid.uuid4().hex[:12]}",
                            "repository_id": repo_id,
                            "source_type": "file",
                            "source_id": file_id,
                            "target_type": "component",
                            "target_id": comp["id"],
                            "type": RelationshipType.USES,
                            "confidence": 0.75,
                            "source_line": None,
                            "evidence": f"Approximate usage of symbol '{comp_name}'"
                        })

        return relationships

    @staticmethod
    def _resolve_python_import(mod_name: str, current_path: str, path_map: Dict[str, str]) -> str | None:
        if not mod_name:
            return None
        parts = mod_name.split('.')
        possible_rel_1 = "/".join(parts) + ".py"
        possible_rel_2 = "/".join(parts) + "/__init__.py"

        for rel_path, file_id in path_map.items():
            if not rel_path:
                continue
            if rel_path == possible_rel_1 or rel_path == possible_rel_2 or rel_path.endswith("/" + possible_rel_1) or rel_path.endswith("/" + possible_rel_2):
                return file_id
        return None

    @staticmethod
    def _resolve_js_import(specifier: str, current_path: str, path_map: Dict[str, str]) -> str | None:
        if not specifier.startswith('.'):
            return None

        current_dir = "/".join(current_path.split("/")[:-1])
        normalized_spec = specifier.lstrip('./')
        candidate = f"{current_dir}/{normalized_spec}" if current_dir else normalized_spec

        possible_exts = ["", ".ts", ".js", ".tsx", ".jsx", "/index.ts", "/index.js"]
        for ext in possible_exts:
            test_path = candidate + ext
            for rel_path, file_id in path_map.items():
                if not rel_path:
                    continue
                if rel_path == test_path or rel_path.endswith(test_path):
                    return file_id
        return None
