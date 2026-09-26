import os
import re
from pathlib import Path
from backend.app.core.config import settings

class IgnoreRuleEvaluator:
    """
    Evaluates whether a directory or file should be skipped during repository analysis.
    Filters:
    - Version control metadata (.git)
    - Dependencies (node_modules, vendor)
    - Build / cache outputs (dist, build, __pycache__)
    - Secrets (.env, private keys)
    - Oversized files (> 1MB)
    - Binary / non-text media files
    """

    SECRET_PATTERNS = [
        re.compile(r"^\.env(\..*)?$", re.IGNORECASE),
        re.compile(r".*\.pem$", re.IGNORECASE),
        re.compile(r".*\.key$", re.IGNORECASE),
        re.compile(r".*id_rsa.*", re.IGNORECASE),
    ]

    BINARY_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar", ".gz",
        ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo", ".db", ".sqlite",
        ".sqlite3", ".bin", ".woff", ".woff2", ".ttf", ".eot"
    }

    @classmethod
    def should_ignore_dir(cls, dir_name: str) -> bool:
        return dir_name in settings.ALWAYS_IGNORE_DIRS or dir_name.startswith(".")

    @classmethod
    def is_secret_file(cls, filename: str) -> bool:
        return any(pattern.match(filename) for pattern in cls.SECRET_PATTERNS)

    @classmethod
    def is_binary_file(cls, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        return ext in cls.BINARY_EXTENSIONS

    @classmethod
    def should_ignore_file(cls, file_path: str, root_path: str) -> tuple[bool, str]:
        path_obj = Path(file_path)
        filename = path_obj.name

        if cls.is_secret_file(filename):
            return True, "Secret file pattern matched"

        if cls.is_binary_file(filename):
            return True, "Binary or media file"

        ext = path_obj.suffix.lower()
        if ext and ext not in settings.ALLOWED_EXTENSIONS:
            return True, f"Unsupported extension {ext}"

        try:
            size = os.path.getsize(file_path)
            if size > settings.MAX_FILE_SIZE_BYTES:
                return True, f"File size ({size} bytes) exceeds maximum allowable limit ({settings.MAX_FILE_SIZE_BYTES} bytes)"
        except Exception as e:
            return True, f"Error accessing file size: {str(e)}"

        return False, ""
