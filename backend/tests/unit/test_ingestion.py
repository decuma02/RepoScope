"""
Unit tests for repository ingestion.

Covers:
- Path validation and boundary enforcement
- Path traversal prevention
- Symlink escape rejection
- Directory ignore rules (.git, node_modules, dist, build, __pycache__ …)
- File ignore rules (binary, secret, too-large, generated lock files)
- Supported file detection (extension allow-list)
- Language detection from extension
- Content-hash computation
- File record persistence (repository + files table rows)
- Repository counter update (files_discovered, files_skipped)
"""

import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.app.core.config import settings
from backend.app.services.ingestion.ignore_rules import IgnoreRuleEvaluator
from backend.app.services.ingestion.ingestion_service import (
    IngestionService,
    _language_for_extension,
    _sha256_of_file,
)
from backend.app.storage.boundary import (
    RepositoryBoundaryError,
    RepositoryBoundaryValidator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the minimal schema needed."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE repositories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            root_label TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            analyzed_at TEXT,
            files_discovered INTEGER DEFAULT 0,
            files_analyzed INTEGER DEFAULT 0,
            files_skipped INTEGER DEFAULT 0,
            components_found INTEGER DEFAULT 0,
            relationships_found INTEGER DEFAULT 0
        );
        CREATE TABLE files (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            path TEXT NOT NULL,
            language TEXT,
            extension TEXT,
            size_bytes INTEGER DEFAULT 0,
            content_hash TEXT,
            status TEXT NOT NULL,
            FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    return conn


def _seed_repo(conn: sqlite3.Connection, repo_id: str, source_path: str) -> None:
    conn.execute(
        """
        INSERT INTO repositories (id, name, source_type, source_path, root_label, status, created_at)
        VALUES (?, 'test', 'local_path', ?, 'root', 'CREATED', '2024-01-01T00:00:00+00:00')
        """,
        (repo_id, source_path),
    )
    conn.commit()


def _write(directory: str, rel_path: str, content: str = "# content\n") -> str:
    """Write a file relative to *directory*, creating parent dirs as needed."""
    full = os.path.join(directory, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return full


# ===========================================================================
# 1. Boundary Validation
# ===========================================================================

class TestBoundaryValidation:

    def test_valid_directory_is_accepted(self, tmp_path):
        result = RepositoryBoundaryValidator.validate_repository_root(str(tmp_path))
        assert os.path.isabs(result)
        assert os.path.isdir(result)

    def test_empty_string_raises(self):
        with pytest.raises(RepositoryBoundaryError):
            RepositoryBoundaryValidator.validate_repository_root("")

    def test_nonexistent_path_raises(self):
        with pytest.raises(RepositoryBoundaryError):
            RepositoryBoundaryValidator.validate_repository_root("/no_such_dir_xyzzy_999")

    def test_file_path_raises(self, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x")
        with pytest.raises(RepositoryBoundaryError):
            RepositoryBoundaryValidator.validate_repository_root(str(f))

    def test_resolved_path_is_absolute(self, tmp_path):
        result = RepositoryBoundaryValidator.validate_repository_root(str(tmp_path))
        assert Path(result).is_absolute()


# ===========================================================================
# 2. Path Traversal Prevention
# ===========================================================================

class TestPathTraversal:

    def test_traversal_via_dotdot_raises(self, tmp_path):
        with pytest.raises(RepositoryBoundaryError):
            RepositoryBoundaryValidator.resolve_safe_path(str(tmp_path), "../outside.txt")

    def test_traversal_via_absolute_raises(self, tmp_path):
        with pytest.raises(RepositoryBoundaryError):
            RepositoryBoundaryValidator.resolve_safe_path(str(tmp_path), "/etc/passwd")

    def test_safe_subpath_is_accepted(self, tmp_path):
        sub = tmp_path / "src" / "main.py"
        sub.parent.mkdir(parents=True)
        sub.write_text("x")
        result = RepositoryBoundaryValidator.resolve_safe_path(str(tmp_path), "src/main.py")
        assert result.endswith(str(Path("src") / "main.py"))

    def test_is_safe_path_traversal_returns_false(self, tmp_path):
        assert RepositoryBoundaryValidator.is_safe_path(str(tmp_path), "../outside") is False

    def test_is_safe_path_within_root_returns_true(self, tmp_path):
        inner = str(tmp_path / "a" / "b.py")
        assert RepositoryBoundaryValidator.is_safe_path(str(tmp_path), inner) is True


# ===========================================================================
# 3. Symlink Safety
# ===========================================================================

class TestSymlinkSafety:

    @pytest.mark.skipif(os.name == "nt", reason="Symlink creation may require privileges on Windows")
    def test_symlink_inside_repo_is_accepted(self, tmp_path):
        real = tmp_path / "real.py"
        real.write_text("x")
        link = tmp_path / "link.py"
        link.symlink_to(real)
        # Link resolves inside the root → safe
        assert RepositoryBoundaryValidator.is_safe_path(str(tmp_path), str(link)) is True

    @pytest.mark.skipif(os.name == "nt", reason="Symlink creation may require privileges on Windows")
    def test_symlink_escaping_repo_is_rejected(self, tmp_path):
        outside = tmp_path.parent / "secret.txt"
        outside.write_text("secret")
        link = tmp_path / "escape_link.txt"
        link.symlink_to(outside)
        assert RepositoryBoundaryValidator.is_safe_path(str(tmp_path), str(link)) is False

    @pytest.mark.skipif(os.name == "nt", reason="Symlink creation may require privileges on Windows")
    def test_resolve_safe_path_symlink_escape_raises(self, tmp_path):
        outside = tmp_path.parent / "evil.txt"
        outside.write_text("evil")
        link = tmp_path / "escape.txt"
        link.symlink_to(outside)
        with pytest.raises(RepositoryBoundaryError):
            RepositoryBoundaryValidator.resolve_safe_path(str(tmp_path), str(link))


# ===========================================================================
# 4. Directory Ignore Rules
# ===========================================================================

class TestDirectoryIgnoreRules:

    @pytest.mark.parametrize("dir_name", [
        ".git", "node_modules", "dist", "build", "__pycache__",
        "vendor", ".venv", "venv", ".next", "coverage", "target", "out",
    ])
    def test_ignored_dirs(self, dir_name):
        assert IgnoreRuleEvaluator.should_ignore_dir(dir_name) is True

    def test_hidden_dir_is_ignored(self):
        assert IgnoreRuleEvaluator.should_ignore_dir(".hidden") is True

    def test_src_dir_is_not_ignored(self):
        assert IgnoreRuleEvaluator.should_ignore_dir("src") is False

    def test_app_dir_is_not_ignored(self):
        assert IgnoreRuleEvaluator.should_ignore_dir("app") is False

    def test_ignored_dirs_not_walked(self, tmp_path):
        """Files inside ignored directories must not appear in discovery results."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("data")

        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        (node_dir / "lodash.js").write_text("x")

        (tmp_path / "main.py").write_text("print('hi')")

        from backend.app.services.ingestion.discovery import RepositoryDiscovery
        files, _ = RepositoryDiscovery.discover_files(str(tmp_path))
        paths = [f["relative_path"] for f in files]
        assert not any(".git" in p for p in paths)
        assert not any("node_modules" in p for p in paths)
        assert any("main.py" in p for p in paths)


# ===========================================================================
# 5. File Ignore Rules
# ===========================================================================

class TestFileIgnoreRules:

    @pytest.mark.parametrize("filename", [
        "image.png", "photo.jpg", "icon.ico", "font.woff2",
        "app.exe", "lib.dll", "module.so",
        "script.pyc", "data.db", "archive.zip",
    ])
    def test_binary_files_ignored(self, filename):
        assert IgnoreRuleEvaluator.is_binary_file(filename) is True

    @pytest.mark.parametrize("filename", [
        ".env", ".env.local", ".env.production",
        "server.pem", "private.key", "id_rsa",
    ])
    def test_secret_files_ignored(self, filename):
        assert IgnoreRuleEvaluator.is_secret_file(filename) is True

    @pytest.mark.parametrize("filename", [
        "package-lock.json", "yarn.lock", "poetry.lock",
        "Pipfile.lock", "Cargo.lock",
    ])
    def test_lock_files_ignored(self, filename):
        assert IgnoreRuleEvaluator.is_ignored_filename(filename) is True

    def test_oversized_file_is_skipped(self, tmp_path):
        big = tmp_path / "big.py"
        # Write slightly over the limit
        big.write_bytes(b"x" * (settings.MAX_FILE_SIZE_BYTES + 1))
        should_ignore, reason = IgnoreRuleEvaluator.should_ignore_file(str(big), str(tmp_path))
        assert should_ignore is True
        assert "size" in reason.lower()

    def test_source_file_within_size_limit_is_accepted(self, tmp_path):
        src = tmp_path / "hello.py"
        src.write_text("print('hello')")
        should_ignore, _ = IgnoreRuleEvaluator.should_ignore_file(str(src), str(tmp_path))
        assert should_ignore is False


# ===========================================================================
# 6. Supported Source File Detection
# ===========================================================================

class TestSupportedFileDetection:

    @pytest.mark.parametrize("ext", [
        ".py", ".js", ".ts", ".jsx", ".tsx",
        ".java", ".go", ".rs", ".cs", ".rb",
        ".c", ".cpp", ".h",
        ".json", ".yml", ".yaml", ".toml", ".md",
        ".html", ".css", ".sh", ".sql",
    ])
    def test_supported_extensions_accepted(self, ext):
        assert ext in settings.ALLOWED_EXTENSIONS

    @pytest.mark.parametrize("ext", [
        ".png", ".exe", ".dll", ".pyc", ".zip", ".mp4",
    ])
    def test_unsupported_extensions_rejected(self, tmp_path, ext):
        f = tmp_path / f"file{ext}"
        f.write_bytes(b"\x00\x01")
        should_ignore, _ = IgnoreRuleEvaluator.should_ignore_file(str(f), str(tmp_path))
        assert should_ignore is True


# ===========================================================================
# 7. Language Detection
# ===========================================================================

class TestLanguageDetection:

    @pytest.mark.parametrize("ext,expected", [
        (".py", "python"),
        (".js", "javascript"),
        (".ts", "typescript"),
        (".jsx", "javascript"),
        (".tsx", "typescript"),
        (".java", "java"),
        (".go", "go"),
        (".rs", "rust"),
        (".cs", "csharp"),
        (".rb", "ruby"),
        (".cpp", "cpp"),
        (".c", "c"),
        (".sh", "shell"),
        (".sql", "sql"),
        (".md", "markdown"),
        (".json", "json"),
        (".yml", "yaml"),
        (".yaml", "yaml"),
    ])
    def test_language_detection(self, ext, expected):
        assert _language_for_extension(ext) == expected

    def test_unknown_extension_returns_bare_name(self):
        assert _language_for_extension(".xyz") == "xyz"


# ===========================================================================
# 8. Content Hash
# ===========================================================================

class TestContentHash:

    def test_hash_matches_manual_sha256(self, tmp_path):
        content = b"hello ingestion\n"
        f = tmp_path / "sample.py"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert _sha256_of_file(str(f)) == expected

    def test_different_content_different_hash(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("content_a")
        b.write_text("content_b")
        assert _sha256_of_file(str(a)) != _sha256_of_file(str(b))

    def test_identical_content_same_hash(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("same")
        b.write_text("same")
        assert _sha256_of_file(str(a)) == _sha256_of_file(str(b))

    def test_missing_file_returns_empty_string(self, tmp_path):
        assert _sha256_of_file(str(tmp_path / "nonexistent.py")) == ""


# ===========================================================================
# 9. IngestionService – full pipeline
# ===========================================================================

class TestIngestionService:

    def _run(self, tmp_path, extra_files=None):
        """Set up a minimal repo dir, run ingestion, return (conn, repo_id)."""
        # Default source files
        _write(str(tmp_path), "src/main.py", "def main(): pass\n")
        _write(str(tmp_path), "src/utils.py", "def helper(): pass\n")
        _write(str(tmp_path), "README.md", "# Repo\n")

        if extra_files:
            for rel, content in extra_files.items():
                _write(str(tmp_path), rel, content)

        conn = _make_db()
        repo_id = "repo_test_001"
        _seed_repo(conn, repo_id, str(tmp_path))

        IngestionService.ingest_repository(conn, repo_id, str(tmp_path))
        return conn, repo_id

    def test_file_records_are_created(self, tmp_path):
        conn, repo_id = self._run(tmp_path)
        rows = conn.execute("SELECT * FROM files WHERE repository_id = ?", (repo_id,)).fetchall()
        assert len(rows) == 3

    def test_relative_paths_use_forward_slashes(self, tmp_path):
        conn, repo_id = self._run(tmp_path)
        rows = conn.execute("SELECT path FROM files WHERE repository_id = ?", (repo_id,)).fetchall()
        for row in rows:
            assert "\\" not in row["path"], f"Windows separator in path: {row['path']}"

    def test_language_field_populated(self, tmp_path):
        conn, repo_id = self._run(tmp_path)
        rows = conn.execute(
            "SELECT language FROM files WHERE repository_id = ? AND extension = '.py'",
            (repo_id,),
        ).fetchall()
        assert all(r["language"] == "python" for r in rows)

    def test_content_hash_populated(self, tmp_path):
        conn, repo_id = self._run(tmp_path)
        rows = conn.execute("SELECT content_hash FROM files WHERE repository_id = ?", (repo_id,)).fetchall()
        assert all(r["content_hash"] for r in rows)

    def test_file_status_is_ready(self, tmp_path):
        conn, repo_id = self._run(tmp_path)
        rows = conn.execute("SELECT status FROM files WHERE repository_id = ?", (repo_id,)).fetchall()
        assert all(r["status"] == "READY" for r in rows)

    def test_repository_counter_updated(self, tmp_path):
        conn, repo_id = self._run(tmp_path)
        row = conn.execute(
            "SELECT files_discovered FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
        assert row["files_discovered"] == 3

    def test_ignored_files_not_ingested(self, tmp_path):
        """Binary and lock files must not produce file records."""
        conn, repo_id = self._run(
            tmp_path,
            extra_files={
                "assets/logo.png": "\x89PNG\r\n\x1a\n",
                "package-lock.json": "{}",
                ".env": "SECRET=1",
            },
        )
        rows = conn.execute("SELECT path FROM files WHERE repository_id = ?", (repo_id,)).fetchall()
        paths = [r["path"] for r in rows]
        assert not any("logo.png" in p for p in paths)
        assert not any("package-lock.json" in p for p in paths)
        assert not any(".env" in p for p in paths)

    def test_git_directory_not_ingested(self, tmp_path):
        """Files inside .git must never appear as file records."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\n")
        conn, repo_id = self._run(tmp_path)
        rows = conn.execute("SELECT path FROM files WHERE repository_id = ?", (repo_id,)).fetchall()
        assert not any(".git" in r["path"] for r in rows)

    def test_invalid_root_path_raises(self, tmp_path):
        conn = _make_db()
        repo_id = "repo_bad"
        _seed_repo(conn, repo_id, "/no_such_path_xyzzy_999")
        with pytest.raises(RepositoryBoundaryError):
            IngestionService.ingest_repository(conn, repo_id, "/no_such_path_xyzzy_999")

    def test_returns_correct_counts(self, tmp_path):
        """ingest_repository must return (discovered, skipped, warnings)."""
        _write(str(tmp_path), "a.py")
        _write(str(tmp_path), "b.py")
        conn = _make_db()
        repo_id = "repo_counts"
        _seed_repo(conn, repo_id, str(tmp_path))
        discovered, skipped, warnings = IngestionService.ingest_repository(
            conn, repo_id, str(tmp_path)
        )
        assert discovered == 2
        assert isinstance(skipped, int)
        assert isinstance(warnings, list)

    def test_size_bytes_recorded(self, tmp_path):
        content = "x" * 100
        _write(str(tmp_path), "sized.py", content)
        conn = _make_db()
        repo_id = "repo_size"
        _seed_repo(conn, repo_id, str(tmp_path))
        IngestionService.ingest_repository(conn, repo_id, str(tmp_path))
        row = conn.execute(
            "SELECT size_bytes FROM files WHERE repository_id = ? AND path LIKE '%sized.py'",
            (repo_id,),
        ).fetchone()
        assert row is not None
        assert row["size_bytes"] == len(content.encode())
