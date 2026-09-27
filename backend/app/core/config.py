import os
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "RepoScope"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api"
    ENVIRONMENT: str = os.getenv("REPOSCOPE_ENV", "development")
    DEBUG: bool = True
    LOG_LEVEL: str = os.getenv("REPOSCOPE_LOG_LEVEL", "INFO")

    # Security & CORS Settings
    # Accepts either a JSON array or a comma-separated string so Railway env vars work naturally:
    #   CORS_ORIGINS=https://reposcope.vercel.app,https://preview.vercel.app
    CORS_ORIGINS: list[str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Watsonx / IBM Granite Credentials
    WATSONX_APIKEY: str = ""
    WATSONX_PROJECT_ID: str = ""
    WATSONX_URL: str = "https://us-south.ml.cloud.ibm.com"
    WATSONX_MODEL_ID: str = "ibm/granite-13b-chat-v2"

    # Optional Fallback LLM Providers
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-70b-versatile"
    OLLAMA_URL: str = ""
    OLLAMA_MODEL: str = "llama3"

    # Database — Railway: set REPOSCOPE_DB_PATH=/data/reposcope.db and mount a persistent volume to /data.
    DATABASE_PATH: str = os.getenv("REPOSCOPE_DB_PATH", "/data/reposcope.db")

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

