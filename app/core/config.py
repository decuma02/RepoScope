import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Repolytic"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_PATH: str = os.path.join(os.getcwd(), "data_store", "repolytic.db")

    # Ingestion & Parsing Limits
    MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB default
    ALLOWED_EXTENSIONS: set[str] = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".md", ".yml", ".yaml", ".toml"
    }
    ALWAYS_IGNORE_DIRS: set[str] = {
        ".git", "node_modules", "vendor", "dist", "build", ".next", "coverage", "__pycache__", ".venv", "venv"
    }

    # AI Context Settings
    MAX_CONTEXT_TOKENS: int = 8000
    CHAT_TIMEOUT_SECONDS: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
