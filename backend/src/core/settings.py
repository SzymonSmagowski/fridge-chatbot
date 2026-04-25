from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    OPENAI_API_KEY: str | None = None
    DEFAULT_MODEL: str = "gpt-4o-mini"
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
    FERNET_KEY: str = "v3wPLJTw45A9mE_b6mIwS5zmpxwPF-43bp9xL9qsQT4="

    # JWT
    SECRET_KEY: str = "changeme"
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

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"

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
