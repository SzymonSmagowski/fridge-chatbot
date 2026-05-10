"""Unit tests for `core/startup_guards.validate_production_secrets` (D3, D4, D5).

Pure logic — no DB, no FastAPI, no network. Each test instantiates a fresh
Settings via `model_copy` so we don't pollute the test_settings fixture.

The guard's job is to refuse to boot in prod when ANY published default is
still in place. In dev (the contributor default) it's a no-op.
"""
from __future__ import annotations

import pytest

from src.core.settings import Settings
from src.core.startup_guards import (
    PUBLISHED_DEFAULT_FERNET_KEY,
    PUBLISHED_DEFAULT_SECRET_KEYS,
    validate_production_secrets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prod_safe_settings(**overrides) -> Settings:
    """A Settings instance that would pass validation in prod, with optional
    targeted overrides to break each guard one at a time.
    """
    base = {
        "ENVIRONMENT": "prod",
        "SECRET_KEY": "a-real-prod-secret-" + "x" * 40,
        "FERNET_KEY": "ZmFrZS1mZXJuZXQta2V5LWZvci10ZXN0LW5vdC1yZWFsLTEyMz0=",
        "ALLOWED_ORIGINS": "https://kiosk.example.com,https://app.example.com",
    }
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Dev no-op
# ---------------------------------------------------------------------------


def test_validate_production_secrets_in_dev_is_a_noop_with_published_defaults() -> None:
    """ENVIRONMENT='dev' (the default for contributors) must NEVER raise,
    even when every published default is in place. Otherwise the dev
    experience breaks on `cp .env.example .env`.
    """
    settings = Settings(
        ENVIRONMENT="dev",
        SECRET_KEY="changeme",
        FERNET_KEY=PUBLISHED_DEFAULT_FERNET_KEY,
        ALLOWED_ORIGINS="http://localhost:3000",
    )
    # Must not raise.
    validate_production_secrets(settings)


# ---------------------------------------------------------------------------
# Prod failure modes — one per guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("default_secret", sorted(PUBLISHED_DEFAULT_SECRET_KEYS))
def test_validate_production_secrets_rejects_published_default_secret_key(
    default_secret: str,
) -> None:
    settings = _prod_safe_settings(SECRET_KEY=default_secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_secrets(settings)


def test_validate_production_secrets_rejects_published_default_fernet_key() -> None:
    settings = _prod_safe_settings(FERNET_KEY=PUBLISHED_DEFAULT_FERNET_KEY)
    with pytest.raises(RuntimeError, match="FERNET_KEY"):
        validate_production_secrets(settings)


def test_validate_production_secrets_rejects_localhost_in_allowed_origins() -> None:
    settings = _prod_safe_settings(
        ALLOWED_ORIGINS="https://kiosk.example.com,http://localhost:3000"
    )
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        validate_production_secrets(settings)


def test_validate_production_secrets_rejects_127_in_allowed_origins() -> None:
    settings = _prod_safe_settings(
        ALLOWED_ORIGINS="https://kiosk.example.com,http://127.0.0.1:3000"
    )
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        validate_production_secrets(settings)


# ---------------------------------------------------------------------------
# Prod happy path
# ---------------------------------------------------------------------------


def test_validate_production_secrets_in_prod_with_clean_overrides_passes() -> None:
    settings = _prod_safe_settings()
    # Must not raise.
    validate_production_secrets(settings)


def test_validate_production_secrets_in_prod_message_includes_actionable_hint() -> None:
    """A failed boot must tell the operator how to fix it.

    Error message contract: includes the offending env var AND a hint on how
    to generate a new one. This is a UX-of-failure test — not asserting on
    exact wording, just that the operator can act on the message.
    """
    settings = _prod_safe_settings(SECRET_KEY="changeme")
    with pytest.raises(RuntimeError) as excinfo:
        validate_production_secrets(settings)
    msg = str(excinfo.value)
    assert "SECRET_KEY" in msg
    assert "secrets.token_urlsafe" in msg or "generate" in msg.lower()
