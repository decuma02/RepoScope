import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RepoScope"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Watsonx / IBM Granite Credentials Placeholder
    WATSONX_APIKEY: str = ""
    WATSONX_PROJECT_ID: str = ""
    WATSONX_URL: str = "https://us-south.ml.cloud.ibm.com"
    WATSONX_MODEL_ID: str = "ibm/granite-13b-chat-v2"

    # Database & Data Paths
    DATABASE_PATH: str = os.getenv("REPOSCOPE_DB_PATH", os.path.join(os.getcwd(), "data", "index", "reposcope.db"))

    # Ingestion & Parsing Limits
    MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB default
    ALLOWED_EXTENSIONS: set[str] = {
        # Python
        ".py", ".pyi",
        # JavaScript / TypeScript
        ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        # Web
        ".html", ".htm", ".css", ".scss", ".less",
        # JVM / compiled
        ".java", ".kt", ".kts", ".groovy", ".scala",
        # C family
        ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
        # Systems
        ".go", ".rs", ".swift",
        # Ruby / PHP
        ".rb", ".php",
        # C# / .NET
        ".cs",
        # Shell / config
        ".sh", ".bash", ".zsh", ".fish",
        # Data / config
        ".json", ".yml", ".yaml", ".toml", ".xml", ".ini", ".cfg", ".conf", ".env.example",
        # Docs / markup
        ".md", ".mdx", ".rst", ".txt",
        # SQL
        ".sql",
        # Dockerfile
        ".dockerfile",
    }
    ALWAYS_IGNORE_DIRS: set[str] = {
        ".git", "node_modules", "vendor",
        "dist", "build", "out", "target",
        ".next", ".nuxt", ".svelte-kit",
        "coverage", ".nyc_output",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".venv", "venv", "env", ".env",
        ".tox", ".eggs", "*.egg-info",
        "tmp", "temp", ".tmp",
        ".idea", ".vscode",
    }

    # Map file extension → canonical language name used in file records
    EXTENSION_LANGUAGE_MAP: dict[str, str] = {
        ".py": "python", ".pyi": "python",
        ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".java": "java",
        ".kt": "kotlin", ".kts": "kotlin",
        ".groovy": "groovy",
        ".scala": "scala",
        ".c": "c", ".h": "c",
        ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
        ".go": "go",
        ".rs": "rust",
        ".swift": "swift",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".fish": "shell",
        ".html": "html", ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".less": "less",
        ".json": "json",
        ".yml": "yaml", ".yaml": "yaml",
        ".toml": "toml",
        ".xml": "xml",
        ".ini": "ini", ".cfg": "ini", ".conf": "ini",
        ".md": "markdown", ".mdx": "markdown",
        ".rst": "rst",
        ".txt": "text",
        ".sql": "sql",
        ".dockerfile": "dockerfile",
    }

    # AI Context Settings
    MAX_CONTEXT_TOKENS: int = 8000
    CHAT_TIMEOUT_SECONDS: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
