from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Deployment environment. 'dev' is the default so a fresh clone boots with
    # contributor-friendly defaults. In 'prod' the startup guards in
    # `core/startup_guards.py` refuse to boot if SECRET_KEY / FERNET_KEY are
    # still the published defaults or ALLOWED_ORIGINS contains localhost.
    ENVIRONMENT: Literal["dev", "prod"] = "dev"

    # LLM
    OPENAI_API_KEY: str | None = None
    DEFAULT_MODEL: str = "gpt-5.4-nano"
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 1000

    # Postgres
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "dev"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    SQL_ECHO: bool = False

    # When true (dev default), `alembic upgrade head` runs on FastAPI lifespan
    # startup. Set false in environments that run migrations out-of-band.
    AUTO_MIGRATE: bool = True

    # Redis (cache, locks, rate-limit storage, pub/sub)
    REDIS_URL: str = "redis://redis:6379"

    # Encryption (Fernet) — used to encrypt Google refresh tokens at rest.
    # MUST be a urlsafe base64-encoded 32-byte key. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Required in ENVIRONMENT=prod (the startup guard refuses to boot when
    # empty). In dev, leave blank and `ensure_dev_fernet_key` in
    # `core/startup_guards.py` auto-generates an ephemeral one on startup.
    FERNET_KEY: str = ""

    # JWT
    SECRET_KEY: str = "changeme-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60480
    DEVICE_TOKEN_EXPIRE_DAYS: int = 365
    BACKEND_DEBUG_API_KEY: str | None = None

    # Bootstrap defaults — written into family_preferences on pairing (D9, D10).
    AUTO_CREATE_SHOPPING_LIST_DEFAULT: bool = True
    SYNC_INTERVAL_SEC_DEFAULT: int = 300

    # Google OAuth (for the calendar feature)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8001/oauth/google/callback"
    GOOGLE_OAUTH_SCOPES: str = (
        "openid email profile https://www.googleapis.com/auth/calendar"
    )

    # Frontend base URL — used for OAuth callback redirects. Backend and
    # frontend run on different origins, so the redirect target must be
    # absolute or the browser stays on the backend origin and 404s.
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Resource monitor — when true, a background task logs the uvicorn
    # process's CPU% / RSS / threads / fd count every few seconds. Useful for
    # local diagnosis of perf regressions; should stay off in production.
    BACKEND_RESOURCE_MONITOR: bool = False
    BACKEND_RESOURCE_MONITOR_INTERVAL_SECONDS: float = 5.0

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"

    # LiveKit (voice transport). The browser connects to LIVEKIT_PUBLIC_URL —
    # which is host-reachable (`ws://localhost:7880` from a host browser).
    # The voice_worker process connects from inside the container network using
    # the service name. Both flow through the same room name + JWT.
    LIVEKIT_URL: str = "ws://livekit-server:7880"
    LIVEKIT_PUBLIC_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"
    LIVEKIT_ROOM_PREFIX: str = "fridge"
    LIVEKIT_TOKEN_TTL_SECONDS: int = 3600

    # Observability
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_HOST: str | None = None
    LANGFUSE_ENABLED: bool = False

    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_PROJECT: str = "fridge-chatbot"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def ALLOWED_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def GOOGLE_OAUTH_SCOPES_LIST(self) -> list[str]:
        return [s.strip() for s in self.GOOGLE_OAUTH_SCOPES.split() if s.strip()]

    def __hash__(self) -> int:
        return hash((self.DEFAULT_MODEL, self.DATABASE_URL, self.SECRET_KEY))
