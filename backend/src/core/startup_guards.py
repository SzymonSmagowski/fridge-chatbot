"""Startup safety guards.

Two responsibilities, both called from `main.lifespan` after settings load
and before alembic runs.

- `validate_production_secrets` — refuse to boot in `ENVIRONMENT=prod` when
  contributor-friendly placeholders are still in place. SECRET_KEY must not
  be a known placeholder, FERNET_KEY must be set, ALLOWED_ORIGINS must not
  contain localhost/127.0.0.1. No-op in dev.

- `ensure_dev_fernet_key` — if FERNET_KEY is empty AND we're in dev, generate
  an ephemeral Fernet key and mutate settings in place. Logs the value so
  the contributor can copy it into their `.env` if they want persistence.
  Lets `cp .env.example .env && ./run.sh` work end-to-end without a manual
  key-generation step, while keeping zero Fernet-shaped strings in source
  (so secret scanners stay quiet on a public repo).
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet

from src.core.settings import Settings

logger = logging.getLogger(__name__)

PUBLISHED_DEFAULT_SECRET_KEYS = {
    "changeme",
    "changeme-use-a-long-random-string",
}


def validate_production_secrets(settings: Settings) -> None:
    """Refuse to boot in prod if any contributor-friendly placeholder is still in place.

    No-op when ENVIRONMENT != 'prod'. Raises RuntimeError with an actionable
    message otherwise — the lifespan lets it propagate so uvicorn exits.
    """
    if settings.ENVIRONMENT != "prod":
        return

    if settings.SECRET_KEY in PUBLISHED_DEFAULT_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY is a published placeholder; refusing to boot in prod. "
            "Generate a new one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )

    if not settings.FERNET_KEY:
        raise RuntimeError(
            "FERNET_KEY is not set; refusing to boot in prod. "
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


def ensure_dev_fernet_key(settings: Settings) -> None:
    """Generate an ephemeral Fernet key in dev if none was provided.

    Mutates `settings.FERNET_KEY` in place. No-op when:
    - ENVIRONMENT == 'prod' (the production requirement is enforced by
      `validate_production_secrets`, which runs first and would have already
      raised if FERNET_KEY were empty)
    - FERNET_KEY is already set
    """
    if settings.ENVIRONMENT == "prod":
        return
    if settings.FERNET_KEY:
        return

    key = Fernet.generate_key().decode("utf-8")
    settings.FERNET_KEY = key
    logger.warning(
        "FERNET_KEY is not set — generated an ephemeral key for this run. "
        "Google OAuth refresh tokens encrypted with this key will become "
        "undecryptable on restart. To make it persistent, add this line to "
        "backend/.env: FERNET_KEY=%s",
        key,
    )
