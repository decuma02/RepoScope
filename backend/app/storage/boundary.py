import os
from pathlib import Path

class RepositoryBoundaryError(Exception):
    pass

class RepositoryBoundaryValidator:
    """
    Ensures filesystem operations are strictly confined within the validated repository root boundary.
    Prevents path traversal and unsafe symlink escapes.
    """

    @staticmethod
    def validate_repository_root(path_str: str) -> str:
        if not path_str or not isinstance(path_str, str):
            raise RepositoryBoundaryError("Repository source path must be a non-empty string.")

        target_path = Path(path_str).resolve()

        if not target_path.exists():
            raise RepositoryBoundaryError(f"Repository root path does not exist: {path_str}")

        if not target_path.is_dir():
            raise RepositoryBoundaryError(f"Repository root must be a directory: {path_str}")

        return str(target_path)

    @staticmethod
    def is_safe_path(root_path_str: str, relative_or_abs_target: str) -> bool:
        """
        Return True only if the target resolves inside the root AND is not a
        symlink that escapes the root boundary.
        """
        root_path = Path(root_path_str).resolve()
        target_path = Path(relative_or_abs_target)

        if not target_path.is_absolute():
            target_path = (root_path / target_path).resolve()
        else:
            target_path = target_path.resolve()

        try:
            target_path.relative_to(root_path)
        except ValueError:
            return False

        # Reject symlinks whose real target resolves outside the root
        if target_path.is_symlink():
            real_target = Path(os.path.realpath(target_path))
            try:
                real_target.relative_to(root_path)
            except ValueError:
                return False

        return True

    @staticmethod
    def resolve_safe_path(root_path_str: str, relative_or_abs_target: str) -> str:
        root_path = Path(root_path_str).resolve()
        target_path = Path(relative_or_abs_target)

        if not target_path.is_absolute():
            target_path = (root_path / target_path).resolve()
        else:
            target_path = target_path.resolve()

        try:
            target_path.relative_to(root_path)
        except ValueError:
            raise RepositoryBoundaryError(
                f"Path traversal detected: {relative_or_abs_target} resolves outside repository root {root_path_str}"
            )

        # Also reject symlinks that escape the root
        if target_path.is_symlink():
            real_target = Path(os.path.realpath(target_path))
            try:
                real_target.relative_to(root_path)
            except ValueError:
                raise RepositoryBoundaryError(
                    f"Symlink escape detected: {relative_or_abs_target} points outside repository root {root_path_str}"
                )

        return str(target_path)
