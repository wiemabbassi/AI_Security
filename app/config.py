import os

class Settings:
    APP_NAME: str = "LLM Security Gateway"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/v1"

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

    POSTGRES_URI: str = os.getenv("POSTGRES_URI", "sqlite:///./security_events.db")

    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    OLLAMA_SAFETY_MODEL: str = os.getenv("OLLAMA_SAFETY_MODEL", "llama3.2:latest")

    POLICY_FILE_PATH: str = os.getenv("POLICY_FILE_PATH", "config/policies.yaml")

    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # ── Langfuse observability ─────────────────────────────────────────────────
    # ⚠️  NEVER commit real keys as defaults.
    # Set LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY as environment variables.
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3001")

    # ── Cloud LLM model (used by LiteLLM when OPENAI_API_KEY is set) ──────────
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── CORS — restrict origins in production (comma-separated list) ──────────
    ALLOWED_ORIGINS: list = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8000,http://localhost:8501"
    ).split(",")

settings = Settings()
