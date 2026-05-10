"""Startup safety guards (D3, D4, D5).

Refuses to boot in production when contributor-friendly defaults are still in
place. Called from `main.lifespan` after settings load and before alembic runs.

Why this exists, in three lines:
- `.env.example` ships the published default Fernet key + a placeholder JWT
  signing key so contributors can `cp .env.example .env && ./run.sh` and have
  a working dev DB. Those defaults are public, so they MUST NOT reach prod.
- ALLOWED_ORIGINS in dev includes `http://localhost:*` for the Next.js dev
  server. Leaving that in prod means any malicious site running on a localhost
  port can read browser-credentialed responses if it tricks the browser into
  thinking it's the kiosk frontend.
- Both checks gate on `ENVIRONMENT == 'prod'`. In dev (the default) they no-op.
"""
from __future__ import annotations

from src.core.settings import Settings

PUBLISHED_DEFAULT_FERNET_KEY = "v3wPLJTw45A9mE_b6mIwS5zmpxwPF-43bp9xL9qsQT4="
PUBLISHED_DEFAULT_SECRET_KEYS = {
    "changeme",
    "changeme-use-a-long-random-string",
}


def validate_production_secrets(settings: Settings) -> None:
    """Refuse to boot in prod if any published default is still in place.

    No-op when ENVIRONMENT != 'prod'. Raises RuntimeError with an actionable
    message otherwise — the lifespan lets it propagate so uvicorn exits.
    """
    if settings.ENVIRONMENT != "prod":
        return

    if settings.SECRET_KEY in PUBLISHED_DEFAULT_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY is a published default; refusing to boot in prod. "
            "Generate a new one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )

    if settings.FERNET_KEY == PUBLISHED_DEFAULT_FERNET_KEY:
        raise RuntimeError(
            "FERNET_KEY is the published default; refusing to boot in prod. "
            "Generate a new one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )

    bad_origins = [
        o
        for o in settings.ALLOWED_ORIGINS_LIST
        if "localhost" in o or "127.0.0.1" in o
    ]
    if bad_origins:
        raise RuntimeError(
            "Refusing to start in prod with localhost in ALLOWED_ORIGINS: "
            f"{bad_origins!r}. Update ALLOWED_ORIGINS to the deployed origins only."
        )
