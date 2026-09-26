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
    - Oversized files (> MAX_FILE_SIZE_BYTES)
    - Binary / non-text / generated files
    """

    SECRET_PATTERNS = [
        re.compile(r"^\.env(\..*)?$", re.IGNORECASE),
        re.compile(r".*\.pem$", re.IGNORECASE),
        re.compile(r".*\.key$", re.IGNORECASE),
        re.compile(r".*id_rsa.*", re.IGNORECASE),
        re.compile(r".*\.p12$", re.IGNORECASE),
        re.compile(r".*\.pfx$", re.IGNORECASE),
        re.compile(r".*\.crt$", re.IGNORECASE),
    ]

    BINARY_EXTENSIONS = {
        # Images
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".tiff", ".webp",
        # Vector / fonts
        ".svg", ".woff", ".woff2", ".ttf", ".eot", ".otf",
        # Documents / archives
        ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        # Executables / compiled
        ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib",
        # Python bytecode
        ".pyc", ".pyo", ".pyd",
        # Databases
        ".db", ".sqlite", ".sqlite3",
        # Generic binary / media
        ".bin", ".dat", ".class", ".jar",
        # Video / audio
        ".mp4", ".mp3", ".wav", ".avi", ".mov", ".mkv", ".flac",
        # Lock files (generated, not source)
        ".lock",
    }

    # Generated / non-source file names to skip regardless of extension
    IGNORED_FILENAMES = {
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        ".DS_Store",
        "Thumbs.db",
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
    def is_ignored_filename(cls, filename: str) -> bool:
        return filename in cls.IGNORED_FILENAMES

    @classmethod
    def should_ignore_file(cls, file_path: str, root_path: str) -> tuple[bool, str]:
        path_obj = Path(file_path)
        filename = path_obj.name

        if cls.is_ignored_filename(filename):
            return True, f"Generated lock/system file: {filename}"

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
