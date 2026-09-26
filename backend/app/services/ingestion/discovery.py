import os
from pathlib import Path
from typing import List, Dict, Any
from backend.app.services.ingestion.ignore_rules import IgnoreRuleEvaluator
from backend.app.storage.boundary import RepositoryBoundaryValidator

class RepositoryDiscovery:
    """
    Discovers files in a repository while adhering to boundary security and ignore rules.
    """

    @staticmethod
    def discover_files(root_path_str: str) -> tuple[List[Dict[str, Any]], List[str]]:
        validated_root = RepositoryBoundaryValidator.validate_repository_root(root_path_str)

        analyzable_files = []
        skipped_warnings = []

        for current_root, dirs, files in os.walk(validated_root):
            dirs[:] = [d for d in dirs if not IgnoreRuleEvaluator.should_ignore_dir(d)]

            for file in files:
                full_path = os.path.join(current_root, file)
                if not RepositoryBoundaryValidator.is_safe_path(validated_root, full_path):
                    skipped_warnings.append(f"Skipped unsafe path: {full_path}")
                    continue

                rel_path = os.path.relpath(full_path, validated_root)
                should_ignore, reason = IgnoreRuleEvaluator.should_ignore_file(full_path, validated_root)

                if should_ignore:
                    skipped_warnings.append(f"Skipped {rel_path}: {reason}")
                    continue

                try:
                    size_bytes = os.path.getsize(full_path)
                    ext = os.path.splitext(file)[1].lower()
                    analyzable_files.append({
                        "full_path": full_path,
                        "relative_path": rel_path.replace("\\", "/"),
                        "extension": ext,
                        "size_bytes": size_bytes
                    })
                except Exception as e:
                    skipped_warnings.append(f"Failed to inspect {rel_path}: {str(e)}")

        return analyzable_files, skipped_warnings
