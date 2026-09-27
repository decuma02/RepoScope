import os
import sqlite3
from typing import Generator
from backend.app.core.config import settings

def _migrate_components_table(conn: sqlite3.Connection) -> None:
    """Add columns introduced in the structure-extraction upgrade (idempotent)."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(components)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "is_exported" not in existing_cols:
        cursor.execute("ALTER TABLE components ADD COLUMN is_exported INTEGER NOT NULL DEFAULT 0")
    if "parent_name" not in existing_cols:
        cursor.execute("ALTER TABLE components ADD COLUMN parent_name TEXT")
    conn.commit()

def ensure_data_directory():
    db_dir = os.path.dirname(settings.DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception:
            pass

def get_db_connection() -> sqlite3.Connection:
    ensure_data_directory()
    try:
        conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
    except sqlite3.OperationalError:
        fallback_path = os.path.join(os.getcwd(), "reposcope.db")
        conn = sqlite3.connect(fallback_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    ensure_data_directory()
    try:
        conn = sqlite3.connect(settings.DATABASE_PATH)
    except sqlite3.OperationalError:
        fallback_path = os.path.join(os.getcwd(), "reposcope.db")
        conn = sqlite3.connect(fallback_path)
    cursor = conn.cursor()

    # Repositories Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repositories (
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
    )
    """)

    # Files Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        path TEXT NOT NULL,
        language TEXT,
        extension TEXT,
        size_bytes INTEGER DEFAULT 0,
        content_hash TEXT,
        status TEXT NOT NULL,
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """)

    # Components Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS components (
        id TEXT PRIMARY KEY,
        file_id TEXT NOT NULL,
        repository_id TEXT NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL,
        signature TEXT,
        summary TEXT,
        is_exported INTEGER NOT NULL DEFAULT 0,
        parent_name TEXT,
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """)

    # Content Chunks Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS content_chunks (
        id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        file_id TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL,
        text TEXT NOT NULL,
        token_estimate INTEGER DEFAULT 0,
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """)

    # Relationships Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS relationships (
        id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        type TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        source_line INTEGER,
        evidence TEXT,
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """)

    # Analysis Jobs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analysis_jobs (
        id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        status TEXT NOT NULL,
        progress REAL DEFAULT 0.0,
        stage TEXT NOT NULL,
        files_discovered INTEGER DEFAULT 0,
        files_analyzed INTEGER DEFAULT 0,
        files_skipped INTEGER DEFAULT 0,
        components_found INTEGER DEFAULT 0,
        relationships_found INTEGER DEFAULT 0,
        warnings TEXT,
        error_message TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    _migrate_components_table(conn)
    conn.close()
