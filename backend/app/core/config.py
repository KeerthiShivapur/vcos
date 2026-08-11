from functools import lru_cache
from typing import Annotated, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "VCOS"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "vcos-dev-secret-change-me-in-production-0f8a2b1c"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 24
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 72
    PASSWORD_MIN_LENGTH: int = 8
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    EMAIL_VERIFICATION_REQUIRED: bool = False

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:keerthi@localhost:5432/vcos2"
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis (optional; graceful degradation if unavailable) ---
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = False

    # --- CORS ---
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3007",
            "http://127.0.0.1:3007",
        ]
    )

    # --- Email (Phase 1: console/log transport) ---
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@vcos.io"
    EMAIL_TRANSPORT: str = "console"  # console | smtp

    # --- AI Gateway (Phase 1 foundation + Phase 7 Universal AI Companion) ---
    # provider: none | local | openai | anthropic | groq
    # `local` (or `none`) uses the built-in deterministic intelligence engine —
    # VCOS works with zero external AI dependencies. Set a GROQ_API_KEY and
    # AI_PROVIDER=groq to use Groq's LLMs for free-form generation.
    AI_PROVIDER: str = "local"
    AI_API_KEY: Optional[str] = None
    AI_BASE_URL: Optional[str] = None
    AI_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    AI_MAX_TOKENS: int = 1024
    AI_RETRIES: int = 2
    AI_CACHE_ENABLED: bool = True

    # --- Embedding gateway (Slice 4D.2) ---
    # The embeddings provider is independent from the LLM provider (AI gateway
    # boundary). The API provider talks to a self-hosted /embeddings endpoint
    # (e.g. Ollama, text-embeddings-inference) or any Groq-compatible gateway
    # reachable via EMBEDDING_BASE_URL — never a vendor-locked OpenAI model.
    # The deterministic provider keeps the system fully offline. Every stored
    # vector records which provider produced it.
    # provider: deterministic | api | groq
    EMBEDDING_PROVIDER: str = "deterministic"
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_BASE_URL: Optional[str] = None  # defaults to AI_BASE_URL
    EMBEDDING_API_KEY: Optional[str] = None  # defaults to AI_API_KEY

    # --- Rate limiting ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return self.CORS_ORIGINS


@lru_cache
def get_settings() -> Settings:
    return Settings()
