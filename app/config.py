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
    OLLAMA_SAFETY_MODEL: str = os.getenv("OLLAMA_SAFETY_MODEL", "llama-guard3:8b")
    
    POLICY_FILE_PATH: str = os.getenv("POLICY_FILE_PATH", "config/policies.yaml")
    
    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-86165bf7-f1a9-4ca5-9f27-41fdd8d5989b")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-2691c0fa-fd59-4a5c-9d5b-3e436e236652")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3001")

settings = Settings()
