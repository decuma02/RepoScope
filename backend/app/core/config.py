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
